import sqlalchemy as sq
from sqlalchemy.orm import sessionmaker
import models as models
import pandas as pd
from sqlalchemy.orm import joinedload
from sqlalchemy import or_, func
from sqlalchemy.exc import SQLAlchemyError
from constants import DEGFilter


class DB():

    # DATABASE_NAME = "test_db.sqlite"
    DATABASE_NAME = "all_xerophyta_species_db.sqlite"
    def __init__(self) -> None:
        
        self.engine = sq.create_engine(f"sqlite:///{self.DATABASE_NAME}", echo = False)
        self.conn = self.engine.connect()

        Session = sessionmaker(bind=self.engine)
        self.session = Session()

    def add_species(self, name):
        species = self.session.query(models.Species).filter_by(name=name).first()
        if not species:
            species = models.Species(name=name)
            self.session.add(species)
            self.session.commit()
        return species
    
    def add_genes_from_fasta(self, species_id, gene_name, coding_seq):
        gene = self.session.query(models.Gene).filter_by(gene_name=gene_name).first()
        if not gene:
            gene = models.Gene(gene_name=gene_name, 
                               species_id=species_id, 
                               coding_sequence=coding_seq)
            self.session.add(gene)
            self.session.commit()

        return gene



    def create_or_update(self, model, values, lookup_fields):
        """
    Generic method to create or update any record in any model and return an instance of that record.

    Works even if the primary key is auto-generated by using a unique lookup field.

    Parameters:
        model: the model (or table) in which to perform the Create or Update task
        values: a list of dictionaries specifying the values the new record should contain
        lookup_field: the field (or unique column) used to identify whether a record exists (e.g., "gene_name", "sequence_name", etc.)
    """
        try:
            instance = None
            total = len(values)
            for idx, value in enumerate(values):
                #query the database using teh lookup field to see if the record exists

                filters = {field: value[field] for field in lookup_fields}
                query = self.session.query(model).filter_by(**filters)
                # Check if an instance exists
                instance = query.first()

                if instance is not None:
                    # print(f"Updating record with {value[lookup_field]}")
                    # Update the existing record
                    for key, val in value.items():
                        setattr(instance, key, val)
                else:
                    # print(f"Creating record with {value[lookup_field]}")
                    # Create a new record
                    instance = model(**value)
                    self.session.add(instance)
                print(f"Processed {idx+1}/{total} records")
            self.session.commit()
            return instance
        except SQLAlchemyError as e:
            self.session.rollback()
            print(e)
            raise e

    def batch_create_or_update(self, model, values, pk):
         
        """ 
        Generic method to create or update any record in any model and return an instance of that record.

            Also works for batch insertions or updates, in which case the last record of the batch job is returned.

            Parameters:
                model: the model (or table) in which to perform the Create or Update task
                values: a list of dictionaries specifying the values the new record should contain
                pk: the primary key of this table, as a string
        """
        batch_size = 1000
        instances = []

        for i, value in enumerate(values):

            instance = self.session.query(model).get(value[pk])
            
            if instance is not None:
                instance = self.session.merge(model(**value))

            else:
                instance = model(**value) 
                self.session.add(instance)

            instances.append(instance)

            # process the records in batches before committing
            if(i+1)% batch_size == 0:
                self.session.commit()
                instances = []

        if instances:
            self.session.commit()
        return instances[-1] if instances else None

    def add_gene_locus(self, model, values):
        """ 
        Update gene_location in the database by mapping it to Hit_acc.

        Parameters:
            model: the model (or table) to update
            df: a pandas DataFrame containing 'Hit_acc' and 'gene_location'
        """

        for i, value in enumerate(values):
            # Find the instance by matching Hit_acc
            instances = self.session.query(model).filter_by(Hit_ACC=value['Hit_ACC']).all()
            
            for instance in instances:
                if instance is not None:
                    instance.At_locus_id = value['At_locus_id']
                    instance.At_gene_name = value['At_gene_name']


        if instances:
            self.session.commit()


    # pass dictionary with 
    def add_at_homologues(self, acc_num, at_locus, common_name_list):
        xe_gene = self.session.query(models.Gene_info).filter(models.Gene_info.Hit_ACC== acc_num).all()
    
        # Step 3: Create or retrieve Arabidopsis homologue data
        # First, check if the homologue already exists
        homologue = self.session.query(models.Arabidopsis_Homologue).filter(models.Arabidopsis_Homologue.accession_number==acc_num).first()

        # If the homologue doesn't exist, create it
        if homologue is None:
            homologue = models.Arabidopsis_Homologue(
                accession_number=acc_num,
                at_locus= at_locus # Example locus
            )
            self.session.add(homologue)

        # Step 4: Add common names
        # Assuming we have multiple common names for this accession number

        for name in common_name_list:
        #     # Check if the common name exists for this homologue
            existing_common_name = self.session.query(models.At_Common_Names).filter_by(name=name, arabidopsis_id=homologue.arabidopsis_id).first()

            if existing_common_name is None:
                common_name = models.At_Common_Names(name=name, homologue=homologue)
                self.session.add(common_name)

        #  Step 5: Associate the XeGene with the Arabidopsis homologue (many-to-many relationship)
        for gene in xe_gene:

            if homologue not in gene.homologues:
                gene.homologues.append(homologue)

        # Step 6: Commit the transaction
        self.session.commit()

    def get_gene_expression_data(self, gene_names, experiment_name, filter_deg=DEGFilter.SHOW_ALL):
        """
        Fetches RNA-seq gene expression data for the specified genes and experiment, applying DEG filtering if required.

        Parameters:
            gene_names (list): List of gene names.
            experiment_name (str): Name of the experiment.
            filter_deg (DEGFilter): DEG filter option (Enum).

        Returns:
            pd.DataFrame: A DataFrame containing the filtered gene expression data.
        """
        query = (
            self.session.query(
                models.Gene_expressions.gene_id,
                models.Gene_expressions.normalised_expression,
                models.Gene_expressions.log2_expression,
                models.Gene_expressions.treatment,
                models.Gene_expressions.time,
                models.Gene_expressions.replicate,
                models.Gene.gene_name
            )
            .join(models.Gene, models.Gene_expressions.gene_id == models.Gene.id)
            .join(models.Experiments, models.Gene_expressions.experiment_id == models.Experiments.id)
            .filter(models.Experiments.experiment_name == experiment_name)
            .filter(models.Gene.gene_name.in_(gene_names))
        )

        # Apply DEG filtering based on the selected option
        if filter_deg == DEGFilter.SHOW_DEG:
            query = query.join(models.DifferentialExpression, models.DifferentialExpression.gene_id == models.Gene.id)
            query = query.filter(
                (models.DifferentialExpression.re_set.isnot(None)) | (models.DifferentialExpression.de_set.isnot(None))
            )
        elif filter_deg == DEGFilter.SHOW_UP:
            query = query.join(models.DifferentialExpression, models.DifferentialExpression.gene_id == models.Gene.id)
            query = query.filter(
                (models.DifferentialExpression.re_direction == "Up-regulated") | (models.DifferentialExpression.de_direction == "Up-regulated")
            )
        elif filter_deg == DEGFilter.SHOW_DOWN:
            query = query.join(models.DifferentialExpression, models.DifferentialExpression.gene_id == models.Gene.id)
            query = query.filter(
                (models.DifferentialExpression.re_direction == "Down-regulated") | (models.DifferentialExpression.de_direction == "Down-regulated")
            )

        # Execute query and return results as a DataFrame
        result = query.all()
        columns = ["gene_id", "normalised_expression", "log2_expression", "treatment", "time", "replicate","gene_name"]
        return pd.DataFrame(result, columns=columns)
    
    
    
    


    def get_species(self):
        """Retrieve all the species from the database.

        Returns:
            List[Species]: A list of Species objects.
        """
        results = self.session.query(models.Species).all()
        return results
    
    def get_gene_by_name(self, gene_name):
        query = self.session.query(models.Gene).filter_by(gene_name=gene_name).first()
        return query
    
    def get_species_by_name(self, species_name):  
        """Retrieve a species object by its name.

        Args:
            species_name (str): The name of the species.

        Returns:
            Species: A Species object
        """
        query = self.session.query(models.Species).filter_by(name=species_name).first()
        return query

    def get_experiments(self):
        results = self.session.query(models.Experiments).all()
        
        return results
    
    def get_experiment_by_name(self, experiment_name):
        """Get an experiment by its name.

        Args:
            experiment_name (str): The name of the experiment.

        Returns:
            Experiments: An Experiments object.
        """
        experiment = self.session.query(models.Experiments).filter_by(experiment_name=experiment_name).first()
        return experiment

    def get_experiments_by_species(self, species_name):
        """
        Retrieve all experiments associated with a given species name.

        Parameters:
            species_name (str): The name of the species.

        Returns:
            List[Experiments]: A list of Experiment objects associated with the species.
        """
        # Query experiments associated with the given species
        results = (
            self.session.query(models.Experiments)
            .join(models.Gene_expressions, models.Experiments.id == models.Gene_expressions.experiment_id)
            .join(models.Species, models.Gene_expressions.species_id == models.Species.id)
            .filter(models.Species.name == species_name)
            .distinct()  # To avoid duplicates
            .all()
        )
        return results

    def link_experiment_to_species(self, experiment_name, species_name):
        
        species = self.get_species_by_name(species_name)
    
        if not species:
            print(f"Species '{species_name}' does not exist in the database.")
            return

        experiment = self.get_experiment_by_name(experiment_name)
        if not experiment:
            print(f"Experiment '{experiment_name}' does not exist in the database.")
            return

        # Step 3: Link the experiment to the species
        if experiment.species is None:
            experiment.species = species
        else:
            print(f"Experiment '{experiment_name}' is already linked to a species '{experiment.species.name}'.")
            return

        # Step 4: Commit the changes
        print(f"Experiment '{experiment_name}' is now linked to species '{species_name}'.")
        self.session.commit()

    def check_if_gene_in_database(self, gene_list):
        """
        Check if a gene is in the database.

        Parameters:
            gene_list (list): A list of gene names to check.

        Returns:
            List[str]: A boolean list if gene is in the database.
        """
        in_db = []
        for gene in gene_list:
            query = self.session.query(models.Gene).filter(models.Gene.gene_name == gene).first()
            if query:
                in_db.append(True)
            else:
                in_db.append(False)
        return in_db
    
    def check_if_go_term_in_database(self, go_terms):
        """
        Check if a GO term is in the database.

        Parameters:
            go_terms (list): A list of GO terms to check.

        Returns:
            List[str]: A boolean list if GO term is in the database.
        """
        in_db = []
        for term in go_terms:
            query = self.session.query(models.GO).filter(
                or_
                (models.GO.go_id.in_(term),models.GO.go_name.in_(term))
                ).first()
       
            if query:
                in_db.append(True)
            else:
                in_db.append(False)
        return in_db


    def get_genes_by_go_term_or_description(self, go_inputs, species_name= None):
        """
        Query genes associated with a list of GO names or GO IDs.

        Parameters:
            go_inputs (list of str): GO names or GO IDs to query.

        Returns:
            List[Gene]: List of Gene objects associated with the GO terms.
        """
        # Preprocess each GO term to handle missing prefixes
        processed_inputs = []
        for term in go_inputs:
            if ":" not in term:
                # Generate possible matches by prepending the valid prefixes
                processed_inputs.extend([f"P:{term}", f"F:{term}", f"C:{term}"])
            else:
                # Directly add the user-provided term
                processed_inputs.append(term)

        # Build query
        query = (
            self.session.query(models.Gene)
            .join(models.Annotation, models.Annotation.gene_id == models.Gene.id)
            .join(models.annotations_go, models.annotations_go.c.annotation_id ==models.Annotation.id)
            .join(models.GO, models.GO.id == models.annotations_go.c.go_id)
            .filter(
                or_(
                    models.GO.go_id.in_(processed_inputs),  # Match any of the possible GO IDs
                    *[models.GO.go_name.ilike(f"%{term}%") for term in go_inputs]  # Match GO names (case-insensitive)
                )
            )
        )
        # Add an optional species filter
        if species_name:
            query = query.join(models.Species, models.Gene.species_id == models.Species.id).filter(
            models.Species.name.ilike(f"%{species_name}%")
        )

        return query.all()

    
    
    def get_gene_annotation_data(self, gene_list):
        
        # ensure its a list
        if isinstance(gene_list, str):
            gene_list = [gene_list]
        
        query = self.session.query(models.Gene_info).filter(models.Gene_info.gene_name.in_(gene_list)).all()

        return query
        
    def get_uniprot_id(self):
        query = self.session.query(models.Gene_info.Hit_ACC).all()
        return query

    def genes_no_info(self):
        results = self.session.query(models.Gene_info.gene_name).filter(models.Gene_info.sequence_description == None).all()
        return results

    def genes_from_seqdata(self):
        results = self.session.query(models.Gene_expressions.gene_name).distinct().all()
        return results
    
    def get_gene_names(self):
        results = self.session.query(models.Gene_info.gene_name).all()
        return results