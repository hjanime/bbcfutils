#!/usr/bin/env python
from bbcflib.motif              import sqlite_to_false_discovery_rate
from bein                       import MiniLIMS, unique_filename_in, ProgramOutput, program, execution
from bbcflib.genrep             import GenRep
from bbcflib.gdv                import create_gdv_project, add_gdv_track, get_project_id
from bbcflib.frontend           import parseConfig
from bbcflib.common             import scp, normalize_url
from bbcflib.track              import Track, new
from os.path                    import basename, expanduser, normcase, splitext, isfile, exists
from os                         import sep
import getopt, sys

usage = """%s [-h] [options] --matrix=/path/to/matrix.mat -c config_file --minilims=minilims_name
-h Print this message and exit
-c --config file Config file
--host submit track file to selected host machine (e.g sugar)
--identity_file public ssh identity file (e.g ~/.ssh/id.rsa)
--matrix file path to matrix
--minilims MiniLIMS where Scanning executions and files will be stored.
--project GDV project name
--remote_path path where put track in host machine
--via via Run executions using method "via" (can be "local" or "lsf")
--username ssh username for login to host
--website website were result will be taken for GDV (e.g http://sugar.epfl.ch)
""" %(sys.argv[0])

class Usage(Exception):
    def __init__(self, msg):
        self.msg = msg

def main(argv = None):
    genrep              = None
    assembly            = None
    M                   = None
    job                 = None
    config              = None
    config_file         = None
    background          = ""
    matrix              = ""
    original_sql_data   = ""
    random_sql_data     = ""
    track_filtered      = ""
    track_scanned       = ""
    project             = ""
    username            = ""
    identity_file       = ""
    host                = ""
    website             = ""
    remote_path         = ""
    result_path         = ""
    via                 = ""
    limspath            = ""
    fdr                 = 0
    runs                = {}
    if argv is None: argv = sys.argv
    try:
        try:
            opts,args = getopt.getopt   (
                                            argv[1:],"hu:c:"  ,
                                            [
                                                "help", "via=", "host="     ,
                                                "remote_path=" , "website=" ,
                                                "minilims=","config="       ,
                                                "matrix=", "username="      ,
                                                "identity_file=", "project="
                                            ]
                                        )
        except getopt.error, msg:
            raise Usage(msg)
        for o, a in opts:
            if o in ("-h", "--help"):
                print __doc__
                print usage
                sys.sys.exit(0)
            elif o == "--via":
                if a=="local":
                    via = "local"
                elif a=="lsf":
                    via = "lsf"
                else:
                    raise Usage("Via (-u) can only be \"local\" or \"lsf\", got %s." % (a,))
            elif o == "--website":
                website = normalize_url(a)
            elif o == "--minilims":
                limspath = normcase(expanduser(a))
            elif o == "--host":
                host = a
            elif o == "--identity_file":
                identity_file = a
            elif o == "--remote_path":
                remote_path = normcase(expanduser(a))
                if not remote_path.endswith(sep): remote_path += sep
            elif o == "--matrix":
                matrix = {basename(a):normcase(expanduser(a))}
            elif o == "--username":
                username = a
            elif o == "--project":
                project = a
            elif o in ("-c", "--config"):
                config_file = normcase(expanduser(a))
            else:
                raise Usage("Unhandled option: " + o)

        # read config file
        if config_file is None or not exists(config_file) or not isfile(config_file):
            raise Usage("Config file missing")
        else:
            job, config = parseConfig(normcase(expanduser(config_file)))

        if project == "": project = job.description
        if matrix == "":
            if "matrix" in job.options:
                matrix = {basename(a):normcase(expanduser(job.options["matrix"]))}
            else:
                raise Usage("You need give a matrix file ")
        if limspath == "":
            if "minilims" in job.options:
                limspath = job.options["minilims"]
            else:
                raise Usage("You need give a minilims path/name")
        if via == "":
            if "via" in job.options:
                via = job.options["via"]
            else:
                via="lsf"
        if host == "" and "host" in job.options:
            host = job.options["host"]
        if identity_file == "" and "identity_file" in job.options:
            identity_file = job.options["identity_file"]
        if remote_path == "" and "remote_path" in job.options:
            remote_path = job.options["remote_path"]
        if username == "" and "username" in job.options:
            username = job.options["username"]
        if website == "" and "website" in job.options:
            website = job.options["website"]

        genrep      = GenRep(config=config)
        assembly    = genrep.assembly(job.assembly_id)
        M           = MiniLIMS(limspath)
        json        = create_gdv_project(
                                            config["gdv"]["key"], config["gdv"]["email"],
                                            project,
                                            assembly.nr_assembly_id,
                                            config["gdv"]["url"],
                                            public = True
                                        )
        project_id  = get_project_id( json )

        # compute false discovery rate
        with execution(M, description=job.description) as ex:
            background = genrep.statistics(assembly,output=unique_filename_in(), frequency=True, matrix_format=True)
            ex.add(background,  description="background:"+background)
            if len(job.groups) >2:
                raise ValueError("They are more than 2 group in config file")

            for group_number in job.groups:
                group = job.groups[group_number]
                for run_number in group["runs"]:
                    r = job.groups[group_number]["runs"][run_number]
                    if "url" in r:
                        url = r["url"]
                        uri = ""
                        if r["run"] not in runs:
                            runs[r["run"]] = {"control":None, "experimental":None}
                        if url.startswith("http") or url.startswith("www."):
                            url = normalize_url(url)
                            # download data
                            data    = urllib2.urlopen(url)
                            uri     = unique_filename_in()
                            with open(run["experimental"], "w") as f:
                                f.write(data.read())
                        else:
                           uri = normcase(expanduser(url))
                        if group["control"]:
                            runs[r["run"]]["control"] = uri
                        else:
                            runs[r["run"]]["experimental"] = uri

            for run in runs:
                current_run         = runs[run]
                original_sql_data   = unique_filename_in()
                random_sql_data     = unique_filename_in()
                track_filtered      = unique_filename_in()

                # convert data to sql
                with Track(current_run["experimental"], chrmeta=assembly.chromosomes) as track:
                    # Get sqlite file if is not arleady in this format
                    if track.format != "sql" or track.format != "db" or track.format != "sqlite":
                        track.convert(original_sql_data, format="sql")
                    else:
                        original_sql_data = current_run["experimental"]
                    # Generate a random population from orginal if it is not give from config file
                    if current_run["control"] is None:
                        # create random track
                        track.shuffle_track(random_sql_data, repeat_number=5)
                    else:
                        with Track(current_run["control"], chrmeta=assembly.chromosomes) as track_random:
                            # Get sqlite file if is not arleady in this format
                            if track_random.format != "sql" or track_random.format != "db" or track_random.format != "sqlite":
                                track_random.convert(random_sql_data, format="sql")
                            else:
                                random_sql_data = current_run["control"]
                ex.add(original_sql_data,   "sql:"+original_sql_data)
                ex.add(random_sql_data,     "sql:"+random_sql_data)
                track_scanned,fdr = sqlite_to_false_discovery_rate(
                                                                    ex,
                                                                    matrix,
                                                                    background,
                                                                    genrep,
                                                                    assembly.chromosomes,
                                                                    original_sql_data,
                                                                    random_sql_data,
                                                                    threshold=0,
                                                                    via=via,
                                                                    keep_max_only=True,
                                                                    alpha=0.05,
                                                                    nb_false_positive_hypotesis=5.0
                                                                  )

                # filter track with fdr as treshold
                with new(track_filtered, format="sql", datatype="qualitative") as track_out:
                    chromosome_used     = {}
                    track_out.meta_track= {"source": basename(current_run["experimental"])}
                    track_out.meta_track.update({"k":"v"})
                    with Track(track_scanned, format="sql", chrmeta=assembly.chromosomes) as track_in:
                        meta = dict([(v["name"],dict([("length",v["length"])])) for v in track_in.chrmeta.values()])
                        for chromosome in track_in.all_chrs:
                            data_list = []
                            for data in track_in.read( {"chr": chromosome, "score": (fdr, sys.maxsize)}, fields=Track.qualitative_fields ):
                                data_list.append(data)
                                chromosome_used[chromosome] = meta[chromosome]
                            if len(data_list) > 0:
                                track_out.write(chromosome, data_list)
                        track_out.chrmeta = chromosome_used
                ex.add(track_filtered,      "sql:"+track_filtered)

                # send new track to remote
                if host != "" and remote_path != "" and username != "":
                    args = []
                    if identity_file != "":
                        args = ["-i", normcase(expanduser(identity_file)), "-C" ]
                    source      = normcase(expanduser(track_filtered))
                    destination = "%s@%s:%s%s%s.db" %(username, host, remote_path, sep, track_filtered)
                    result_path = "%s%s%s.db" %(website, sep, track_filtered)
                    scp(ex, source, destination, args=args)
                else:
                    result_path = track_filtered

                add_gdv_track  (
                                    config["gdv"]["key"], config["gdv"]["email"],
                                    project_id, result_path,
                                    gdv_url=config["gdv"]["url"]
                                )
    except Usage, err:
        print >>sys.stderr, err.msg
        print >>sys.stderr, usage
        return 2
if __name__ == "__main__":
    sys.exit(main())
