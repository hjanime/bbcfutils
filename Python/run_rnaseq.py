#!/bin/env python
"""
A High-throughput RNA-seq analysis workflow.

python run_rnaseq.py -v lsf -c config_files/jobbamtest.txt -d rnaseq -p genes
"""
import os, sys, json, re
import optparse
from bbcflib import rnaseq, frontend, common, mapseq, genrep, email
from bein.util import use_pickle, add_pickle
from bein import execution, MiniLIMS

class Usage(Exception):
    def __init__(self,  msg):
        self.msg = msg

def main():
    map_args = None # {'bwt_args':["-n",str(3),"-p",str(4),"-d",str(50),"--chunkmbs",str(1024),"-m",str(5)]}

    opts = (("-v", "--via", "Run executions using method 'via' (can be 'local' or 'lsf')", {'default': "lsf"}),
            ("-k", "--key", "Alphanumeric key specifying the job", {'action': "store_true", 'default': None}),
            ("-d", "--minilims", "MiniLIMS where RNAseq executions and files will be stored.", {'default': None}),
            ("-m", "--mapseq-minilims", "MiniLIMS where a previous Mapseq execution and files has been stored. \
                                     Set it to None to align de novo from read files.",
                                     {'default': "/data/htsstation/mapseq/mapseq_minilims", 'dest':"ms_limspath"}),
            ("-w", "--working-directory", "Create execution working directories in wdir",
                                     {'default': os.getcwd(), 'dest':"wdir"}),
            ("-c", "--config", "Config file", {'default': None}),
            ("-p", "--pileup_level", "Target features, inside of quotes, separated by commas.\
                                     E.g. 'genes,exons,transcripts'",{'default': "genes"}))
    try:
        usage = "run_rnaseq.py [OPTIONS]"
        desc = """A High-throughput RNA-seq analysis workflow. It returns a file containing
                  a column of transcript counts for each given BAM file, normalized using DESeq's
                  size factors. """
        parser = optparse.OptionParser(usage=usage, description=desc)
        for opt in opts:
            parser.add_option(opt[0],opt[1],help=opt[2],**opt[3])
        (opt, args) = parser.parse_args()

        if os.path.exists(opt.wdir): os.chdir(opt.wdir)
        else: parser.error("Working directory '%s' does not exist." % a)
        if not opt.minilims: parser.error("Must specify a MiniLIMS to attach to")
        if opt.pileup_level: pileup_level = opt.pileup_level.split(',')

        # Rna-seq job configuration
        M = MiniLIMS(opt.minilims)
        if opt.key:
            gl_dict = {
            'genrep_url': 'http://bbcftools.vital-it.ch/genrep/',
            'bwt_root': '/db/genrep/',
            'fastq_root': '/scratch/cluster/daily/htsstation/mapseq/',
            'hts_mapseq': {'url': 'http://htsstation.vital-it.ch/mapseq/',
                           'download': 'http://htsstation.vital-it.ch/lims/mapseq/mapseq_minilims.files/'},
            'hts_rnaseq': {'url': 'http://htsstation.vital-it.ch/rnaseq/',
                           'download': 'http://htsstation.vital-it.ch/lims/rnaseq/rnaseq_minilims.files/'},
            'gdv': {'url': 'http://svitsrv25.epfl.ch/gdv','email': 'jacques.rougemont@epfl.ch',
                    'key': 'ah6kr9fm4nqogijamd3tmclihf'},
            'lims': {'user': 'jrougemont','passwd': {'lgtf': 'cREThu6u','gva': 'wAs2th'}},
            'email': {'sender': 'webmaster.bbcf@epfl.ch','smtp': 'lipidx.vital-it.ch'},
            'script_path': '/mnt/common/epfl/share' }

            M.delete_alias("global variables")
            with execution( M, description='create global variables' ) as ex:
                add_pickle( ex, gl_dict, alias="global variables" )

            gl = use_pickle( M, "global variables" )
            htss = frontend.Frontend( url=gl['hts_rnaseq']['url'] )
            job = htss.job(opt.key)
            [M.delete_execution(x) for x in M.search_executions(with_description=opt.key,fails=True)]
            description = opt.key
        elif os.path.exists(opt.config):
            (job,gl) = frontend.parseConfig( opt.config )
            description = "Job run from config file %s" % opt.config
        else: raise ValueError("Need either a job key (-k) or a configuration file (-c).")

        job.options['ucsc_bigwig'] = job.options.get('ucsc_bigwig') or True
        job.options['gdv_project'] = job.options.get('gdv_project') or False
        job.options['discard_pcr_duplicates'] = job.options.get('discard_pcr_duplicates') or False
        assembly_id = job.assembly_id
        g_rep = genrep.GenRep( gl['genrep_url'], gl.get('bwt_root'), intype=1 )
            #intype is for mapping on the genome (intype=0), exons (intype=1) or transcriptome (intype=2)
        assembly = g_rep.assembly(assembly_id)

        # Retrieve mapseq output
        mapseq_url = None
        if 'hts_mapseq' in gl: mapseq_url = gl['hts_mapseq']['url']

        # Program body #
        with execution(M, description=description, remote_working_directory=opt.wdir ) as ex:
            if opt.ms_limspath == "None":
                print "Alignment..."
                job = mapseq.get_fastq_files( job, ex.working_directory)
                fastq_root = os.path.abspath(ex.working_directory)
                bam_files = mapseq.map_groups(ex, job, fastq_root, assembly_or_dict=assembly, map_args=map_args)
                print "Reads aligned."
            else:
                print "Loading BAM files..."
                (bam_files, job) = mapseq.get_bam_wig_files(ex, job, minilims=opt.ms_limspath, hts_url=mapseq_url,
                                                            script_path=gl.get('script_path') or '', via=opt.via )
                print "Loaded."
            assert bam_files, "Bam files not found."
            print "Current working directory:", ex.working_directory
            rnaseq.rnaseq_workflow(ex, job, assembly, bam_files, pileup_level=pileup_level, via=opt.via)
        # End of program body #

        common.results_to_json(M, ex.id)

        # GDV
        allfiles = common.get_files(ex.id, M)
        if 'gdv_project' in job.options and 'sql' in allfiles:
            allfiles['url'] = {job.options['gdv_project']['public_url']: 'GDV view'}
            download_url = gl['hts_rnapseq']['download']
            [gdv.add_gdv_track( gl['gdv']['key'], gl['gdv']['email'],
                                job.options['gdv_project']['project_id'],
                                url=download_url+str(k),
                                name = re.sub('\.sql','',str(f)),
                                gdv_url=gl['gdv']['url'] )
             for k,f in allfiles['sql'].iteritems()]
        print json.dumps(allfiles)

        # E-mail
        if 'email' in gl:
            r = email.EmailReport( sender=gl['email']['sender'],
                                   to=str(job.email),
                                   subject="RNA-seq job "+str(job.description),
                                   smtp_server=gl['email']['smtp'] )
            r.appendBody('''
Your RNA-seq job is finished. \n
The description was:
'''+str(job.description)+'''
and its unique key is '''+opt.key+'''.\n
You can retrieve the results at this url:
'''+gl['hts_chipseq']['url']+"jobs/"+opt.key+"/get_results")
            r.send()

        sys.exit(0)
    except Usage, err:
        print >>sys.stderr, err.msg
        print >>sys.stderr, usage
        return 2


if __name__ == '__main__':
    sys.exit(main())

