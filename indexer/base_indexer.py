import logging
import django_rq

from algoliasearch import algoliasearch
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.test.client import RequestFactory

algolia_settings = settings.ALGOLIA
APP_ID = algolia_settings['APPLICATION_ID']
API_KEY = algolia_settings['API_KEY']

logger = logging.getLogger('indexer')

class BaseIndexer(object):
    serializer_class = None
    index_name = None

    def __init__(self):
        if not self.serializer_class:
            raise NotImplementedError
        if not self.index_name:
            raise NotImplementedError
        if not self.model:
            raise NotImplementedError

        '''Initializes the index.'''
        client = algoliasearch.Client(APP_ID, API_KEY)
        self.__client = client
        self.__set_index(client)

    def __set_index(self, client):
        '''Get an instance of Algolia Index'''
        self.__index = client.init_index(self.index_name)
        self.__tmp_index = client.init_index(self.index_name + '_tmp')

    def get_objectID(self, instance):
        key = self.get_property_for_objectID()
        return getattr(instance, key)

    def get_property_for_objectID(self):
        return 'id'

    def index_all_queryset(self):
        return self.model.objects.all()

    def index_partial_queryset(self, list_of_objectID):
        kwargs = {'{0}__{1}'.format(self.get_property_for_objectID(), 'in'): list_of_objectID}
        return self.model.objects.filter(**kwargs)

    def build_object(self, instance):
        user = AnonymousUser()

        #quick fix
        SERVER_NAME = "localhost:8000"
        context = dict(request=RequestFactory().get('/', SERVER_NAME=SERVER_NAME))

        context['request'].user = user
        request = context['request']
        ser = self.serializer_class(instance,
            context=context)
        obj = ser.data

        # convert to camelcase
        res = recursive_key_map(underscore_to_camelcase, obj)

        # attach objectID
        res['objectID'] =  self.get_objectID(instance)
        return res

    def reindex_one(self, objectID):
        self.reindex_partial([objectID])
        logger.info('UPDATED %s OBJECT %s', objectID, self.index_name)

    def reindex_delete_one(self, objectID):
        self.reindex_delete_partial([objectID])
        logger.info('DELETED %s OBJECT %s', objectID, self.index_name)

    def reindex_delete_partial(self, list_of_objectID, batch_size=150):
        counts = 0
        result = None
        batch = []

        for idx, objectId in enumerate(list_of_objectID):
            batch.append(objectId)
            if len(batch) >= batch_size:
                result = self.__index.delete_objects(batch)
                logger.info('DELETE %d OBJECTS ON %s', len(batch),
                            self.index_name)
                batch = []
            counts += 1
        if len(batch) > 0: #handle when batch is not all cleared
            result = self.__index.delete_objects(batch)
            logger.info('DELETE %d OBJECTS ON %s', len(batch),
                            self.index_name)
            counts += 1

        # Assume all items are deleted
        return counts

    def reindex_partial(self, list_of_objectID, batch_size=150):
        qs = self.index_partial_queryset(list_of_objectID)

        counts = 0
        result = None
        batch = []

        for idx, instance in enumerate(qs):
            builded_object = self.build_object(instance)
            print 'building object (', idx + 1, '/', len(qs), ')', builded_object.get('url')
            batch.append(builded_object)
            if len(batch) >= batch_size:
                result = self.__index.save_objects(batch)
                logger.info('SAVE %d OBJECTS TO %s', len(batch),
                            self.index_name)
                batch = []
            counts += 1
        if len(batch) > 0: #handle when batch is not all cleared
            result = self.__index.save_objects(batch)
            logger.info('SAVE %d OBJECTS TO %s', len(batch),
                            self.index_name)
            counts += 1

        # Assume all items are reindexed
        return counts

    def reindex_all(self, batch_size=150, async=False):
        qs = self.index_all_queryset()

        '''Spawn workers '''
        counts = 0
        batch_counts = 0
        result = None
        objectIDs = []

        for idx, instance in enumerate(qs):
            objectIDs.append(self.get_objectID(instance))
            if len(objectIDs) >= batch_size:
                if async:
                    django_rq.enqueue(self.reindex_partial, objectIDs)
                else:
                    self.reindex_partial(objectIDs)
                batch_counts += 1
                objectIDs = []
            counts += 1
        if len(objectIDs) > 0: #handle when batch is not all cleared
            if async:
                django_rq.enqueue(self.reindex_partial, objectIDs)
            else:
                self.reindex_partial(objectIDs)
            batch_counts += 1
        print 'Spawning ' + str(batch_counts) + ' tasks'

        '''Update Settings'''
        self.update_settings()

        print 'Done'


    def update_settings(self):
        self.__index.set_settings(self.get_index_setting_dict())
        print 'Settings updated'

    def rebuild_all(self, batch_size=150):
        qs = self.index_all_queryset()

        '''Reindex all records.'''
        self.__tmp_index.clear_index()
        logger.debug('CLEAR INDEX %s_tmp', self.index_name)

        counts = 0
        result = None
        batch = []

        for idx, instance in enumerate(qs):
            builded_object = self.build_object(instance)
            print 'building object (', idx + 1, '/', len(qs), ')', builded_object.get('url')
            batch.append(builded_object)
            if len(batch) >= batch_size:
                result = self.__tmp_index.save_objects(batch)
                logger.info('SAVE %d OBJECTS TO %s_tmp', len(batch),
                            self.index_name)
                batch = []
            counts += 1
        if len(batch) > 0: #handle when batch is not all cleared
            result = self.__tmp_index.save_objects(batch)
            logger.info('SAVE %d OBJECTS TO %s_tmp', len(batch),
                            self.index_name)

        self.__tmp_index.set_settings(self.get_index_setting_dict())

        if result:
            self.__client.move_index(self.index_name + '_tmp', self.index_name)
            # self.__client.
            logger.info('MOVE INDEX %s_tmp TO %s', self.index_name,
                        self.index_name)
        return counts

    def get_index_setting_dict(self):
        return {
            "attributesToIndex": [],
            "attributesForFaceting": [],
            "attributesToRetrieve": [],
            "customRanking": [],
            "attributesToHighlight": [],
            "synonyms": []
        }

def is_camel(s):
    return (s != s.lower() and s != s.upper())

# Helper to convert to camelcase
def underscore_to_camelcase(word, lower_first=True):
    if not is_camel(word):
        result = ''.join(char.capitalize() for char in word.split('_'))
        if lower_first:
            return result[0].lower() + result[1:]
        else:
            return result
    return word

def recursive_key_map(function, obj):
    if isinstance(obj, dict):
        new_dict = {}
        for key, value in obj.iteritems():
            if isinstance(key, basestring):
                key = function(key)
            new_dict[key] = recursive_key_map(function, value)
        return new_dict
    if hasattr(obj, '__iter__'):
        return [recursive_key_map(function, value) for value in obj]
    else:
        return obj
