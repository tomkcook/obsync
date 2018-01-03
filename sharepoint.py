import json
from pathlib import Path
from pprint import pprint
from collections import abc

from office365.runtime.auth.authentication_context import AuthenticationContext
from office365.runtime.client_request import ClientRequest
from office365.runtime.utilities.request_options import RequestOptions
from office365.runtime.utilities.http_method import HttpMethod

def quote_plus(s):
    if isinstance(s, Path):
        return s
    return s.replace("'", "''")

def authenticate(fn):
    def authenticated(self, *args, **kwargs):
        if not self.connected: self.connect()
        if not self.connected: return None
        return fn(self, *args, **kwargs)
    return authenticated

class FFItem():
    @property
    def name(self):
        return self.path.name

    @property
    def parent(self):
        return self.parent

    @property
    def timestamp(self):
        return self.data['TimeLastModified']

    def relative_to(self, folder):
        return self.path.relative_to(folder.path)

    def delete(self):
        return self.sp.delete(self.path, self.is_folder)

class File(FFItem):
    def __init__(self, sp, path, parent=None, data=None):
        self.sp = sp
        if data is None:
            self.data = self.sp.get("GetFileByServerRelativeUrl('{}')".format(path))
        else:
            self.data = data
        try:
            self.path = Path(self.data['ServerRelativeUrl'])
        except KeyError:
            raise FileNotFoundError(path)
        if parent is None:
            self.parent_obj = Folder(sp, self.path.parent, None)
        self.parent_obj = parent

    def __iter__(self):
        return [].__iter__()

    @property
    def is_folder(self):
        return False

    def read(self, size=1024):
        return self.sp.get_raw("GetFileByServerRelativeUrl('{}')/$value?binaryStringResponseBody=true"
                            .format(self.data['ServerRelativeUrl'])
        ).iter_content(chunk_size=size)

    @property
    def length(self):
        return self.data['Length']

class Folder(FFItem):
    def __init__(self, sp, path, parent = None, data = None):
        self.sp = sp
        self.parent_obj = parent
        if data is None:
            self.data = self.sp.get("GetFolderByServerRelativeUrl('{}')".format(path))
        else:
            self.data = data
        try:
            self.path = Path(self.data['ServerRelativeUrl'])
        except KeyError:
            raise FileNotFoundError(path)

    def __iter__(self):
        data = self.sp.get("GetFolderByServerRelativeUrl('{}')?$expand=Folders,Files".format(self.path))
        if 'Folders' not in data:
            pprint(data)
        children = ([Folder(self.sp, f['ServerRelativeUrl'], self, f) for f in data['Folders']] +
                    [File(self.sp, f['ServerRelativeUrl'], self, f) for f in data['Files']])
        return children.__iter__()

    def __getitem__(self, name):
        path = Path(self.data['ServerRelativeUrl']) / name
        data = self.sp.get("GetFolderByServerRelativeUrl('{}')".format(path))
        if 'odata.error' in data:
            data = self.sp.get("GetFileByServerRelativeUrl('{}')".format(path))
        else:
            return Folder(self.sp, path, self, data)
        if 'odata.error' in data:
            raise ValueError(name)
        else:
            return File(self.sp, path, self, data)

    @property
    def is_folder(self):
        return True

    @property
    def is_empty(self):
        return self.data['ItemCount'] == 0

class SharePoint():
    def __init__(self, url, username, password):
        self.site_url = url
        if self.site_url[-1] != '/':
            self.site_url += '/'
        self.username = username
        self.password = password
        self.connected = False

    def connect(self):
        self.ctx_auth = AuthenticationContext(self.site_url)
        self.connected = self.ctx_auth.acquire_token_for_user(self.username, self.password)
        self.request = ClientRequest(self.ctx_auth)
        print('Authentication was {}successful'.format('not ' if not self.connected else ''))
        return self.connected

    @authenticate
    def get(self, path):
#        request = ClientRequest(self.ctx_auth)
        options = RequestOptions('{}_api/web/{}'.format(self.site_url, path))
        options.set_header('Accept', 'application/json')
        options.set_header('Content-Type', 'application/json')
        data = self.request.execute_request_direct(options)
        if data.status_code == 404:
            raise ValueError('Site does not exist')
        s = json.loads(data.content)
        return s

    @authenticate
    def get_raw(self, path):
#        request = ClientRequest(self.ctx_auth)
        options = RequestOptions('{}_api/web/{}'.format(self.site_url, path))
        data = self.request.execute_request_direct(options)
        return data

    @authenticate
    def post_raw(self, path, headers = {}, data = {}):
        options = RequestOptions('{}{}'.format(self.site_url, path))
        options.method = HttpMethod.Post
        options.set_headers(headers)
        if isinstance(data, abc.Mapping):
            options.data.update(data)
        data = self.request.execute_request_direct(options)
        if data.status_code == 403:
            print(options.url)
            print(data.content)
            print(options.headers)
        return data

    @authenticate
    def post(self, path, headers = {}, data = {}):
#        request = ClientRequest(self.ctx_auth)
        options = RequestOptions('{}_api/web/{}'.format(self.site_url, path))
        options.method = HttpMethod.Post
        options.set_headers(headers)
        options.data = data
        data = self.request.execute_request_direct(options)
        if data.status_code == 403:
            print(options.url)
            print(data.content)
            print(options.headers)
        return data

    def get_digest(self):
        data = self.post_raw('_api/contextinfo', headers=dict(Accept='application/json; odata=verbose'))
        data = json.loads(data.content)
        return data['d']['GetContextWebInformation']['FormDigestValue']

    def lists(self):
        return self.get('lists')

    def get_list(self, name):
        return self.get("lists/getbytitle('{}')".format(quote_plus(name)))

    def get_list_items(self, name):
        return self.get("lists/getbytitle('{}')/Items".format(quote_plus(name)))

    def get_folder(self, path):
        return Folder(self, path, None)

    def get_file(self, path):
        return File(self, path)

    def find_file(self, root, path):
        file = self.get_folder(root)
        for x in path.components:
            file = file[x]
        return file

    def delete(self, path, is_folder=False):
        form_digest = self.get_digest()
        return self.post("Get{}ByServerRelativeUrl('{}')".format('Folder' if is_folder else 'File', path),
            headers = { 'X-RequestDigest': form_digest,
                        'IF-MATCH': 'etag or "*"',
                        'X-HTTP-Method': 'DELETE'})

    def create_file(self, path, f, size):
        form_digest = self.get_digest()
        return self.post("GetFolderByServerRelativeUrl('{}')/Files/add(url='{}', overwrite=true)".format(path.parent, path.name),
            headers = { 'X-RequestDigest': form_digest,
                        'Content-Length': str(size)},
            data = f)

    def create_folder(self, path):
        form_digest = self.get_digest()
        return self.post("folders",
            headers = { 'X-RequestDigest': form_digest,
                        'accept': 'application/json;odata=verbose',
                        'content-type': 'application/json;odata=verbose'},
            data = { '__metadata': { 'type': 'SP.Folder' },
                     'ServerRelativeUrl': str(path)})
