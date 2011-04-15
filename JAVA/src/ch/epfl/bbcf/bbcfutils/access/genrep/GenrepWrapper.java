package ch.epfl.bbcf.bbcfutils.access.genrep;

import java.io.IOException;
import java.util.List;

import org.codehaus.jackson.type.TypeReference;

import ch.epfl.bbcf.bbcfutils.access.genrep.Constants.FORMAT;
import ch.epfl.bbcf.bbcfutils.access.genrep.Constants.KEY;
import ch.epfl.bbcf.bbcfutils.access.genrep.Constants.METHOD;
import ch.epfl.bbcf.bbcfutils.access.genrep.json_pojo.Assembly;
import ch.epfl.bbcf.bbcfutils.access.genrep.json_pojo.Chromosome;
import ch.epfl.bbcf.bbcfutils.access.genrep.json_pojo.Genome;
import ch.epfl.bbcf.bbcfutils.access.genrep.json_pojo.GenrepObject;
import ch.epfl.bbcf.bbcfutils.access.genrep.json_pojo.NR_Assembly;
import ch.epfl.bbcf.bbcfutils.access.genrep.json_pojo.Organism;

public class GenrepWrapper {


	public static Chromosome guessChromosome(String guessable, int assemblyId) throws MethodNotFoundException, IOException {
		@SuppressWarnings("unchecked")
		List<Chromosome> chromosomes = (List<Chromosome>) GenRepAccess.doQueryList(
				Constants.URL, METHOD.INDEX, FORMAT.json, new TypeReference<List<GenrepObject>>() {},KEY.chromosomes,
				"assembly_id="+assemblyId+"&identifier="+guessable);
		if(!chromosomes.isEmpty()){
			return chromosomes.get(0);
		}
		return null;
	}



	public static Assembly getAssemblyFromNrAssemblyId(int id) throws MethodNotFoundException, IOException {
		@SuppressWarnings("unchecked")
		List<Assembly> assemblies = (List<Assembly>) GenRepAccess.doQueryList(
				Constants.URL, METHOD.ALL, FORMAT.json, new TypeReference<List<GenrepObject>>() {},KEY.assemblies,null);
		for(Assembly assembly : assemblies){
			if(assembly.getNr_assembly_id()==id){
				return assembly;
			}
		}
		return null;
	}



	public static NR_Assembly getNrAssemblyFromId(int id) throws IOException, MethodNotFoundException, ClassNotFoundException {
		return (NR_Assembly) GenRepAccess.doQuery(
				Constants.URL, METHOD.SHOW, FORMAT.json, NR_Assembly.class,KEY.nr_assemblies, id);
	}



	/**
	 * Get an Assembly from it's id
	 * @param id - the id of the assembly
	 * @throws IOException
	 * @throws MethodNotFoundException
	 * @throws ClassNotFoundException
	 * @return an Assembly
	 */
	public static Assembly getAssemblyFromId(int id) throws IOException, MethodNotFoundException, ClassNotFoundException{
		return (Assembly) GenRepAccess.doQuery(
				Constants.URL, METHOD.SHOW, FORMAT.json, Assembly.class,KEY.assemblies, id);
	}

	/**
	 * Get a genome from it's id
	 * @param id - the genome identifier
	 * @return a Genome
	 * @throws ClassNotFoundException 
	 * @throws MethodNotFoundException 
	 * @throws IOException 
	 */
	public static Genome getGenomeFromId(int id) throws IOException, MethodNotFoundException, ClassNotFoundException {
		return (Genome) GenRepAccess.doQuery(
				Constants.URL, METHOD.SHOW, FORMAT.json, Genome.class,KEY.genomes, id);
	}

	/**
	 * Get all organisms present in Genrep
	 * @return A List of Organism
	 * @throws IOException 
	 * @throws MethodNotFoundException 
	 */
	@SuppressWarnings("unchecked")
	public static List<Organism> getOrganisms() throws MethodNotFoundException, IOException {
		return (List<Organism>) GenRepAccess.doQueryList(
				Constants.URL, METHOD.ALL, FORMAT.json, new TypeReference<List<GenrepObject>>() {},KEY.organisms,null);
	}


}
