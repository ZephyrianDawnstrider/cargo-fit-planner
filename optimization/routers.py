class MultiDBRouter:
    """
    A database router to direct database operations for specific models
    to their designated databases.
    """

    def db_for_read(self, model, **hints):
        """
        Direct read operations for models to their respective databases.
        """
        if model._meta.app_label == 'optimization':
            if model.__name__ == 'Containertypes':
                return 'default'  # linkerkyc database
            elif model.__name__ == 'Dimensions':
                return 'database_Dimensions'  # linkercalc database
        return None

    def db_for_write(self, model, **hints):
        """
        Direct write operations for models to their respective databases.
        """
        if model._meta.app_label == 'optimization':
            if model.__name__ == 'Containertypes':
                return 'default'  # linkerkyc database
            elif model.__name__ == 'Dimensions':
                return 'database_Dimensions'  # linkercalc database
        return None

    def allow_relation(self, obj1, obj2, **hints):
        """
        Allow relations between objects from the same database.
        """
        if obj1._meta.app_label == 'optimization' and obj2._meta.app_label == 'optimization':
            return True
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        """
        Prevent migrations for database-first models.
        """
        if app_label == 'optimization':
            return False
        return None
