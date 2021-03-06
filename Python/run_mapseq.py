#!/usr/bin/env python

"""
A High-throughput sequencing data mapping workflow.

"""
from bein.util import use_pickle, add_pickle
from bbcflib import daflims, genrep, frontend, email, gdv
from bbcflib.common import get_files, set_file_descr, track_header
from bbcflib.mapseq import *
import sys, getopt, os, re

usage = """run_mapseq.py [-h] [-u via] [-w wdir] [-k job_key] [-c config_file] -d minilims

-h           Print this message and exit
-u via       Run executions using method 'via' (can be "local" or "lsf")
-w wdir      Create execution working directories in wdir
-d minilims  MiniLIMS where mapseq executions and files will be stored.
-k job_key   Alphanumeric key specifying the job
-c file      Config file
"""

class Usage(Exception):
    def __init__(self,  msg):
        self.msg = msg

def main(argv = None):
    via = "lsf"
    limspath = None
    hts_key = ''
    working_dir = None
    config_file = None
    if argv is None:
        argv = sys.argv
    try:
        try:
            opts,args = getopt.getopt(sys.argv[1:],"hu:k:d:w:c:",
                                      ["help","via=","key=","minilims=",
                                       "working-directory=","config="])
        except getopt.error, msg:
            raise Usage(msg)
        for o, a in opts:
            if o in ("-h", "--help"):
                print __doc__
                print usage
                return 0
            elif o in ("-u", "--via"):
                if a=="local":
                    via = "local"
                elif a=="lsf":
                    via = "lsf"
                else:
                    raise Usage("Via (-u) can only be \"local\" or \"lsf\", got %s." % (a,))
            elif o in ("-w", "--working-directory"):
                if os.path.exists(a):
                    os.chdir(a)
                    working_dir = a
                else:
                    raise Usage("Working directory '%s' does not exist." % a)
            elif o in ("-d", "--minilims"):
                limspath = a
            elif o in ("-k", "--key"):
                hts_key = a
            elif o in ("-c", "--config"):
                config_file = a
            else:
                raise Usage("Unhandled option: " + o)
        if not(limspath and os.path.exists(limspath)
               and (hts_key != None or (config_file and os.path.exists(config_file)))):
            raise Usage("Need a minilims and a job key or a configuration file")
        M = MiniLIMS( limspath )
        if len(hts_key)>1:
            gl = use_pickle(M, "global variables")
            htss = frontend.Frontend( url=gl['hts_mapseq']['url'] )
            job = htss.job( hts_key )
            [M.delete_execution(x) for x in M.search_executions(with_description=hts_key,fails=True)]
        elif os.path.exists(config_file):
            (job,gl) = frontend.parseConfig( config_file )
            hts_key = job.description
        else:
            raise ValueError("Need either a job key (-k) or a configuration file (-c).")
        g_rep = genrep.GenRep( url=gl["genrep_url"], root=gl["bwt_root"],
                               intype=job.options.get('input_type_id') or 0 )
        assembly = g_rep.assembly( job.assembly_id )
        if 'lims' in gl:
            dafl = dict((loc,daflims.DAFLIMS( username=gl['lims']['user'], password=pwd ))
                        for loc,pwd in gl['lims']['passwd'].iteritems())
        else:
            dafl = None
        if not('compute_densities' in job.options):
            job.options['compute_densities'] = True
        elif isinstance(job.options['compute_densities'],str):
            job.options['compute_densities'] = job.options['compute_densities'].lower() in ['1','true','t']
        if not('ucsc_bigwig' in job.options):
            job.options['ucsc_bigwig'] = True
        elif isinstance(job.options['ucsc_bigwig'],str):
            job.options['ucsc_bigwig'] = job.options['ucsc_bigwig'].lower() in ['1','true','t']
        job.options['ucsc_bigwig'] = job.options['ucsc_bigwig'] and job.options['compute_densities']
        if not('create_gdv_project' in job.options):
            job.options['create_gdv_project'] = False
        elif isinstance(job.options['create_gdv_project'],str):
            job.options['create_gdv_project'] = job.options['create_gdv_project'].lower() in ['1','true','t']
        if job.options.get('read_extension'):
            job.options['read_extension'] = int(job.options['read_extension'])
        if job.options.get('merge_strands'):
            job.options['merge_strands'] = int(job.options['merge_strands'])
        logfile = open(hts_key+".log",'w')
        with execution( M, description=hts_key, remote_working_directory=working_dir ) as ex:
            logfile.write("Enter execution, fetch fastq files.\n");logfile.flush()
            job = get_fastq_files( job, ex.working_directory, dafl )
            logfile.write("Map reads.\n");logfile.flush()
            mapped_files = map_groups( ex, job, ex.working_directory, assembly, {'via': via} )
            logfile.write("Make stats:\n");logfile.flush()
            for k,v in job.groups.iteritems():
                logfile.write(str(k)+str(v['name'])+"\t");logfile.flush()
                pdf = add_pdf_stats( ex, mapped_files,
                                     {k:v['name']},
                                     gl.get('script_path') or '',
                                     description=set_file_descr(v['name']+"_mapping_report.pdf",groupId=k,step='stats',type='pdf') )
            if job.options['compute_densities']:
                logfile.write("computing densities.\n");logfile.flush()
                if not(job.options.get('read_extension')>0):
                    job.options['read_extension'] = mapped_files.values()[0].values()[0]['stats']['read_length']
                density_files = densities_groups( ex, job, mapped_files, assembly.chromosomes, via=via )
                logfile.write("Finished computing densities.\n");logfile.flush()
                if job.options['create_gdv_project']:
                    logfile.write("Creating GDV project.\n");logfile.flush()
                    gdv_project = gdv.create_gdv_project( gl['gdv']['key'], gl['gdv']['email'],
                                                          job.description,
                                                          assembly.nr_assembly_id,
                                                          gdv_url=gl['gdv']['url'], public=True )
                    logfile.write("GDV project: "+str(gdv_project['project_id']+"\n"));logfile.flush()
                    add_pickle( ex, gdv_project, description=set_file_descr("gdv_json",step='gdv',type='py',view='admin') )
        allfiles = get_files( ex.id, M )
        if 'ucsc_bigwig' and g_rep.intype == 0:
            ucscfiles = get_files( ex.id, M, select_param={'ucsc':'1'} )
            with open(hts_key+".bed",'w') as ucscbed:
                for ftype,fset in ucscfiles.iteritems():
                    for ffile,descr in fset.iteritems():
                        if re.search(r' \(.*\)',descr): continue
                        ucscbed.write(track_header(descr,ftype,gl['hts_mapseq']['download'],ffile))
        if job.options['create_gdv_project']:
            allfiles['url'] = {gdv_project['public_url']: 'GDV view'}
            download_url = gl['hts_mapseq']['download']
            [gdv.add_gdv_track( gl['gdv']['key'], gl['gdv']['email'],
                                gdv_project['project_id'],
                                url=download_url+str(k),
                                name = re.sub('\.sql','',str(f)),
                                gdv_url=gl['gdv']['url'] )
             for k,f in allfiles['sql'].iteritems()]
        logfile.close()
        print json.dumps(allfiles)
        with open(hts_key+".done",'w') as done:
            json.dump(allfiles,done)
        if 'email' in gl:
            r = email.EmailReport( sender=gl['email']['sender'],
                                   to=str(job.email),
                                   subject="Mapseq job "+str(job.description),
                                   smtp_server=gl['email']['smtp'] )
            r.appendBody('''
Your mapseq job has finished.

The description was:
'''+str(job.description)+'''
and its unique key is '''+hts_key+'''.

You can now retrieve the results at this url:
'''+gl['hts_mapseq']['url']+"jobs/"+hts_key+"/get_results")
            r.send()
        return 0
    except Usage, err:
        print >>sys.stderr, err.msg
        print >>sys.stderr, usage
        return 2

if __name__ == '__main__':
    sys.exit(main())
