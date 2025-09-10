from django.db import models

# Database-first models from linkerkyc database
class Containertypes(models.Model):
    id = models.AutoField(db_column='Id', primary_key=True)
    name = models.TextField(db_column='Name', db_collation='SQL_Latin1_General_CP1_CI_AS')
    size = models.TextField(db_column='Size', db_collation='SQL_Latin1_General_CP1_CI_AS')
    length_m = models.DecimalField(db_column='Length_m', max_digits=18, decimal_places=2)
    breadth_m = models.DecimalField(db_column='Breadth_m', max_digits=18, decimal_places=2)
    height_m = models.DecimalField(db_column='Height_m', max_digits=18, decimal_places=2)
    volume_cbm = models.DecimalField(db_column='Volume_cbm', max_digits=18, decimal_places=2)
    maxpayload_kg = models.DecimalField(db_column='MaxPayload_kg', max_digits=18, decimal_places=2)
    description = models.TextField(db_column='Description', db_collation='SQL_Latin1_General_CP1_CI_AS')
    isdeleted = models.BooleanField(db_column='IsDeleted')
    status = models.BooleanField(db_column='Status')
    createddate = models.DateTimeField(db_column='CreatedDate')
    modifieddate = models.DateTimeField(db_column='ModifiedDate')
    categorytypeid = models.IntegerField(db_column='CategoryTypeId')

    class Meta:
        managed = False
        db_table = 'ContainerTypes'
        app_label = 'optimization'

# Database-first models from linkercalc database
class Dimensions(models.Model):
    queryid = models.IntegerField(db_column='QueryId')  # Changed to IntegerField since Clientdetails model is not available
    Lenght = models.DecimalField(db_column='Lenght', max_digits=18, decimal_places=2)  # Note: Database has typo 'Lenght'
    Breadth = models.DecimalField(db_column='Breadth', max_digits=18, decimal_places=2)
    Height = models.DecimalField(db_column='Height', max_digits=18, decimal_places=2)
    dimensionunit = models.TextField(db_column='DimensionUnit', db_collation='Latin1_General_CI_AI')
    WeightPerUnit = models.TextField(db_column='WeightPerUnit', db_collation='Latin1_General_CI_AI')
    TotalUnits = models.DecimalField(db_column='TotalUnits', max_digits=18, decimal_places=2)
    PackageType = models.TextField(db_column='PackageType', db_collation='Latin1_General_CI_AI')
    CargoType = models.TextField(db_column='CargoType', db_collation='Latin1_General_CI_AI')
    BasePackageWeight = models.DecimalField(db_column='BasePackageWeight', max_digits=18, decimal_places=2)
    dimensionisexpanded = models.BooleanField(db_column='dimensionIsExpanded')
    id = models.AutoField(db_column='Id', primary_key=True)

    class Meta:
        managed = False
        db_table = 'Dimensions'
        app_label = 'optimization'
