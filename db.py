import sqlalchemy as sq
from sqlalchemy.orm import sessionmaker
from sqlalchemy import or_
import models as models
import pandas as pd

class DB():

    DATABASE_NAME = "xerophyta_db.sqlite"

    def __init__(self) -> None:
        
        self.engine = sq.create_engine(f"sqlite:///{self.DATABASE_NAME}", echo = False)
        self.conn = self.engine.connect()

        Session = sessionmaker(bind=self.engine)
        self.session = Session()

    def create_or_update(self, model, values, pk):
        """
        Generic method to create or update any record in any model and return an instance of that record.

        Also works for batch insertions or updates, in which case the last record of the batch job is returned.

        Parameters:
            model: the model (or table) in which to perform the Create or Update task
            values: a list of dictionaries specifying the values the new record should contain
            pk: the primary key of this table, as a string
        """


        for value in values:

            instance = self.session.query(model).get(value[pk])
            
            if instance is not None:

                instance = self.session.merge(model(**value))
                self.session.commit()

            else:
                instance = model(**value) 
                self.session.add(instance)
                self.session.commit()


        return instance

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


    def get_gene_expression_data(self, gene_list):
        """
        Query the database to retrieve gene expression data for a list of genes.

        Parameters:
            gene_list (list): A list of gene names to query.

        Returns:
            pandas.DataFrame: A DataFrame containing the gene expression data.
        """
        # Ensure gene_names is a list or tuple
        if isinstance(gene_list, str):
            gene_list = [gene_list]
        
        query = self.session.query(models.Gene_expressions).filter(models.Gene_expressions.gene_name.in_(gene_list)).all()
        
        data = [record.__dict__ for record in query]

        # Remove SQLAlchemy internal keys (_sa_instance_state)
        for row in data:
            row.pop('_sa_instance_state', None)

        df = pd.DataFrame(data)
        return df

    def get_gene_from_arab_homolog(self, At_list):
        
        query = self.session.query(models.Gene_info.gene_name, models.Gene_info.At_gene_name, models.Gene_info.At_locus_id).filter(
            or_(
            models.Gene_info.At_locus_id.in_(At_list),
            # *[models.Gene_info.At_gene_name.like(f'%{gene}%') for gene in At_list]
            models.Gene_info.At_gene_name.in_(At_list)
            )
        ).all()
        

        # Extract the genes from the query results
        matched_genes = {result.At_gene_name for result in query}
        [print(gene) for gene in matched_genes]
        # Find which genes didn't match
        unmatched_genes = [gene for gene in At_list if gene not in matched_genes]
        print(unmatched_genes)


        return query, unmatched_genes
    
    def get_gene_from_arab_name(self, At_list):
        
        query = self.session.query(models.Gene_info.gene_name, models.Gene_info.At_gene_name).filter(
            *[models.Gene_info.At_gene_name.like(f'%{gene}%') for gene in At_list]
            ).all()
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