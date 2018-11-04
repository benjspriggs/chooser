#!/usr/bin/python3
# get-photo.py
# generate random img url
# respond with JSON obj

import os
import cgitb
import json
import random
import codecs, sys
import requests
import mimetypes
import logging

encode = sys.getfilesystemencoding() # set system encoding

# enable web-side debugging
# cgitb.enable()
# enable debug statements to STDOUT
# logging.basicConfig(level=logging.DEBUG)

def copen(f, m="r"):
    """
    Open a file object with a specific encoding and mode via codecs.open.
    """
    logging.debug("opening f: '%s'", f)
    return codecs.open(f.encode(encode), encoding=encode, mode=m)

def touch(data, filename):
    """
    Puts a dictionary to file.
    """
    logging.debug("writing data to filename: '%s'", filename)
    with copen(filename, 'w') as out:
        json.dump(data, out)

def get_json(filename):
    """
    Returns a dictionary read from the filename.
    """
    logging.debug("getting json from filename: '%s'", filename)
    with copen(filename) as json_file:
        j = json.load(json_file, encoding=encode)
    return j

# give an img url response to a request
def give_response(data, status = "success"):
    response_headers =  ['Content-Type: application/json',\
                'Access-Control-Allow-Origin: *', \
                'Access-Control-Allow-Methods: GET', \
                'Access-Control-Allow-Headers: Content-Type']
    print('\n'.join(response_headers))
    print()
    print(json.dumps({"status":status, "data": data}))
    print()

def generate_cached_image(cache_prefix, auth):
    """
    Returns a function that shrinks an image
    via tinify. If nothing is done, the original image
    is returned.
    """
    logging.debug("generating wrapper...")
    def wrapped(img):
        """
        Requests that an image is shrunk via tinify,
        updates the dictionary accordingly.
        """
        logging.debug("attempting to generate cache for: %s", json.dumps(img))
        if img.get('cached', False):
            logging.debug("was cached")
            # skip
            return img

        r = requests.post("https://api.tinify.com/shrink",
                auth=auth,
                json={ "source": { "url": img['url'] } },
                headers={ 'Content-Type': 'application/json' })

        img['original_url'] = img['url']
        img['last_cached'] = r.headers["Date"]

        if r.status_code is not requests.codes.created:
            logging.debug("got an error for '%s', continuing", img['url'])
            img['error'] = r.status_code
            return img

        img.pop('error', None)

        response = json.loads(r.content.decode("utf-8"))
        # contains the response url
        url = response["output"]["url"]
        mime_type = response["output"]["type"]

        # write the new cached image
        r = requests.get(url)
        fn = os.path.basename(url)
        if not os.path.exists("cache"):
            os.makedirs("cache")
        new_url = os.path.join("cache", fn + mimetypes.guess_extension(mime_type))
        with open(new_url, 'wb') as f:
            f.write(r.content)
        img['url'] = cache_prefix + new_url
        img['cached'] = True
        return img
    return wrapped

def sha1(filename):
    import hashlib
    BLOCKSIZE = 65536
    hasher = hashlib.sha1()
    with open(filename, 'rb') as afile:
        buf = afile.read(BLOCKSIZE)
        while len(buf) > 0:
            hasher.update(buf)
            buf = afile.read(BLOCKSIZE)
    return hasher.hexdigest()

def sha1_dict(d):
    import hashlib
    hasher = hashlib.sha1()
    hasher.update(json.dumps(d).encode("utf-8"))
    return hasher.hexdigest()

class Chooser:
    def __init__(self, settings_path):
        """
        Initialize a Chooser instance from settings.

        settings_path: str
        """
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.debug("getting settings from '%s'", settings_path)

        self.s = get_json(settings_path) # get settings
        self.config = self.s['config']

        root = os.path.join(self.config['root'], self.config['app-root'])
        self.urls_path = os.path.join(root, self.config['urls-path'])
        self.manifest_path = os.path.join(root, 'manifest.json')

    def respond(self):
        """
        Responds to a GET request by choosing an image from the cache,
        or downloading any new images where possible
        """
        self.logger.debug("responding...")

        try:
            p = get_json(self.manifest_path) # get urls
        except Exception:
            p = {}

        self.update_cache(p)

        # attempt to blow through the rest
        # of our TinyPNG cache
        p = self.download_uncached(p)

        try:
            give_response(random.choice([img for img in filter(Chooser.is_valid, p['img'])]))
        except Exception:
            self.logger.debug("no images to work with")
            give_response(None, "failure")

    @staticmethod
    def fetch(img):
        if 'cached' in img and img['cached']:
            return img
        logging.debug("fetching %s", img)
        r = requests.get(img['url'])
        if r.status_code is not requests.codes.ok:
            logging.debug("unable to fetch '%s'", img['url'])
            img['error'] = r.status_code
        else:
            logging.debug("successfully fetched '%s'", img['url'])
            img['mime_type'] = r.headers.get('Content-Type', 'img/jpeg')
        return img

    def update_cache(self, poss = { 'img': [] }):
        """
        Completely rebuilds the cache from the file at self.urls_path.
        """
        urls_hash = sha1(self.urls_path)

        if 'hash' in poss and poss['hash'] == urls_hash:
            return
        self.logger.debug("urls hash was not up to date")
        self.logger.debug("updating cache")
        poss['hash'] = urls_hash

        self.logger.debug("get the current set of urls")
        urls = []
        with copen(self.urls_path) as u:
            urls = set([i.strip('\n') for i in u.readlines()])
            logging.debug("got urls: %s", urls)

        # and load any old cached images
        from glob import glob
        poss['img'] = [{ 'url': url } for url in urls]
        cached_images = glob(self.config['cache-prefix'] + "/*")
        poss['img'].extend([{ 'url': self.config['cache-prefix'] + fn, 'mime_type': mimetypes.guess_type(fn)[0], 'cached': True } for fn in cached_images])

        poss['img'] = [Chooser.fetch(img) for img in poss['img']]
        poss = Chooser.with_valid_imgs(poss)

        # update the manifest
        self.update_manifest(poss)

        # re-write the valid urls
        self.logger.debug("fetched: %s", poss['img'])
        self.update_urls([img['url'] for img in poss['img']])

    @staticmethod
    def is_valid(img):
        return 'error' not in img

    @staticmethod
    def valid_urls(imgs):
        logging.debug("got images to filter: %s", json.dumps(imgs))
        return [img['url'] for img in filter(Chooser.is_valid, imgs)]

    @staticmethod
    def with_valid_imgs(manifest):
        """
        Returns the manifest with validated urls.
        """
        manifest['img'] = [img for img in filter(Chooser.is_valid, manifest['img'])]
        return manifest

    def update_manifest(self, manifest):
        manifest['id'] = sha1_dict(manifest)
        with copen(self.manifest_path, 'w') as out:
            json.dump(manifest, out)

    def update_urls(self, valid_urls):
        self.logger.debug("updating valid urls to be: %s", valid_urls)
        with copen(self.urls_path, 'w') as v_out:
            v_out.writelines([url + '\n' for url in valid_urls])

    def download_uncached(self, manifest):
        key = self.config['api-key']
        auth = requests.auth.HTTPBasicAuth('api', key)

        if key is None:
            return

        cache = generate_cached_image(self.config['cache-prefix'], auth)
        manifest['img'] = [cache(img) for img in manifest['img']]
        self.logger.debug("generated caches for: %s", json.dumps(manifest))
        self.update_manifest(manifest)
        return manifest

if __name__ == "__main__":
    c = Chooser(".settings")

    c.respond()
