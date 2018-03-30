from __future__ import print_function

# ==============================================================================================
# Rooster fetcher. (Nov 2017)
#
# Description:
#
#  Fetch either single episodes or full seasons of episodes from roosterteeth.
#
# Requirements:
#
#  Python 2.7.13 (not 3+)
#
# To set up environment, run commands...
#
#  cd path/to/rooster
#  python -m pip install -r requirements.txt
#
# Settings:
#
#  Edit a copy of file "settings - sample.py" inside Rooster dir and save named as "settings.py"
#
# Application, run...
#  python rooster.py
#
# ==============================================================================================
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#
# Details (what to expect):
#
#  Help documentation is added here and to settings.py.
#
#  Given one or more account details in settings.py and a set of urls,
#  log in to roosterteeth, then fetch and parse episode m3u8 format meta files.
#  For each episode meta file, download and parse available resolutions and associated file list urls.
#  Starting with the highest resolution parsed, download its video url list file.
#  With the url list file, download each .ts video part therein.
#  Output hashes after each part is successfully downloaded, output percentage progress at 5, 20, 40, 60, 80 and 95%
#  For any error during transmission, fallback to the next highest known quality.
#  A template variable in the settings file allows the saved video filename a configurable output format.
#  If output filepath exists in a flatfile db, the episode download is skipped.
#  ffmpeg is used to join video parts into an mvk file by default or an mp4 file if mp4 is found in a url.
#  ffmpeg (win32) exists in the /bin/ folder, any other platforms ffmpeg binary must be placed under the same location.
#  Resolution and quality tag is used in the final video filename, for example...
#  final file can be called <show_parent/rt-podcast/2017/rt-podcast.S2017E465.#465.1080p.WEBRip.mkv
#  A Ctrl+C handler has been added to intercept and gracefully abort at any time instead of exiting immediately. Part
#  downloaded files will be allowed to complete and ffmpeg joined to produce a percentage of the full video and clean
#  up temporary files.
#
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

import datetime
import os
import pickle
import random
import re
import signal
import subprocess
import sys
import time
import warnings

import_ok = True
try:
    # noinspection PyUnresolvedReferences
    from settings import (client_creds, site_url, free_access_only, urls, paranoid_mode, test_mode, test_num_snatch,
                          show_parent, ep_ext, bad_chars, season_template, ep_template, ep_append_title, ffmpeg_bin)
except ImportError:
    print('Edit a copy of file "settings - sample.py" inside Rooster dir and save named as "settings.py"')
    import_ok = False

try:
    # noinspection PyUnresolvedReferences
    from settings import temp_files
except ImportError:
    print('New settings need adding to your settings file. See temp_files in "settings - sample.py"')
    import_ok = False

try:
    # noinspection PyUnresolvedReferences
    import requests
except ImportError:
    print('Requests library missing, inside Rooster dir, do a # pip install -r requirements.txt')
    import_ok = False

try:
    # noinspection PyUnresolvedReferences
    from simple_requests import Requests, ResponsePreprocessor
except ImportError:
    print('simple_requests library missing, inside Rooster dir, do a # pip install -r requirements.txt')
    import_ok = False

if not import_ok:
    exit(1)

warnings.filterwarnings('ignore', module=r'.*connectionpool.*')


def _print(msg):
    print(msg, end='')


def save_obj(obj, filename):
    try:
        with open(filename, 'wb') as fh:
            pickle.dump(obj, fh, pickle.HIGHEST_PROTOCOL)
        return True
    except (StandardError, Exception):
        print('Error saving: %s' % filename)


def load_obj(filename):
    if os.path.isfile(filename):
        try:
            with open(filename, 'rb') as fh:
                return pickle.load(fh)
        except (StandardError, Exception):
            print('Error loading %s' % filename)


def save_userlist():
    global userlist
    if userlist:
        return save_obj(userlist, userdb)
    else:
        try:
            os.remove(userdb)
        except (StandardError, Exception):
            pass


# delay to avoid server side suspicion of automation
def sleep_random():

    if not paranoid_mode:
        return
    global slept
    t = random.choice([float(i) / 10 for i in range(11, 32, 2)])
    slept += t
    time.sleep(t)


def urlkey(url_value):
    return re.sub('[^A-Za-z0-9]', '', url_value)


def remove(saved_files):
    for fname in saved_files:
        try:
            os.remove(fname)
        except (IOError, OSError):
            pass


def sig_handler(signum=None, _=None):
    global abort
    is_ctrlbreak = 'win32' == sys.platform and signal.SIGBREAK == signum
    msg = u'Signal "%s" found' % (signal.SIGINT == signum and 'CTRL-C' or is_ctrlbreak and 'CTRL+BREAK' or
                                  signal.SIGTERM == signum and 'Termination' or signum)
    if None is signum or signum in (signal.SIGINT, signal.SIGTERM) or is_ctrlbreak:
        print('Abort %s, saving and exiting, (can take time)...' % msg)
        abort = True
    else:
        print('%s, not exiting' % msg)


class RespProcessor(ResponsePreprocessor):

    def success(self, bundle):

        if bundle.response.ok:
            # ensure the data dir can be created
            path = meta[urlkey(url)]['ep_path']
            if not os.access(path, os.F_OK):
                try:
                    os.makedirs(path, 0o744)
                except os.error:
                    print(u'Unable to create dir: %s' % path)

            save_name = os.path.join(temp_files, bundle.request.url.rsplit('/', 1)[-1])
            try:
                with open(save_name, 'wb') as fh:
                    fh.write(bundle.response.content)
            except (StandardError, Exception):
                print('Error saving: %s' % save_name)

        return super(RespProcessor, self).success(bundle)


# ####
# Main
# ####
# If CTRL-C pressed, this will gracefully exit saving current downloading parts
abort = False
signal.signal(signal.SIGINT, sig_handler)
signal.signal(signal.SIGTERM, sig_handler)
if 'win32' == sys.platform:
    signal.signal(signal.SIGBREAK, sig_handler)

userdb = os.path.join(os.path.realpath(os.path.dirname(__file__)), 'rooster_user.db')
now = datetime.datetime.now()
slept = 0

userlist = load_obj(userdb) or {}
users = userlist.keys()
changed = False
# add new accounts and update passwords for existing accounts
for u, p in client_creds:
    if u not in userlist or userlist[u]['password'] != p:
        changed = True
    userlist[u] = {
        'password': p,
    }
    try:
        users.remove(u)
    except ValueError:
        pass

# delete non exiting accounts from list
for u in users:
    try:
        del userlist[u]
        changed = True
    except IndexError:
        pass

if changed:
    save_userlist()
    changed = False


ffmpeg_buffer = None
try:
    ffmpeg_buffer = subprocess.Popen([ffmpeg_bin, '-version'],
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT).communicate()
    ffmpeg_version = re.findall(r'(?sim)^(.*?version\s+[^\s]+)', ''.join([out for out in ffmpeg_buffer if out]))[0]
    print('ffmpeg found: %s' % ffmpeg_version)
except OSError:
    print('Error: Ffmpeg not installed, check that its executable is installed at: %s' % ffmpeg_bin)
    exit(1)
except IndexError:
    print('Error: Ffmpeg with version not found, check that its executable is installed at: %s' % ffmpeg_bin)
    exit(1)

if not re.search('(?i)^(?:[a-z]:[\\]|[/])', temp_files):
    temp_files = os.path.join(os.path.dirname(os.path.abspath(__file__)), temp_files)
if not os.access(temp_files, os.F_OK):
    try:
        os.makedirs(temp_files, 0o744)
    except os.error:
        print(u'Unable to create required temp dir: %s' % temp_files)
        exit(1)


test_msg = ('', ' (Test mode, first 3 episode parts are fetched)')[bool(test_mode)]
test_bars = '-' * len(test_msg)
print('-------------------------' + test_bars)
print('Rooster - Content fetcher' + test_msg)
print('-------------------------' + test_bars)


num_member_access = 0
num_saved = 0
num_creds = len(userlist)
concurrent_fetches = 5
# noinspection PyCompatibility
for username, userdata in userlist.iteritems():

    start = time.time()

    req = Requests(concurrent=concurrent_fetches, defaultTimeout=20)
    session = req.session
    session.verify = False
    session.headers.update({'User-Agent': 'Mozilla/5.0 (compatible; MSIE 10.0; Windows NT 6.1; Trident/6.0)',
                            'Accept-Encoding': 'gzip,deflate'})

    print('Fetching Client Area login page for username: %s' % username)
    try:
        sleep_random()
        resp = req.one('%s/login' % site_url)
        if abort:
            break
    except (StandardError, Exception):
        resp = None
    if not resp:
        print('Issue requesting login page from server')
        continue

    if 'Login' not in resp.content:
        print('Issue finding html login form, check html for updates')
        continue

    try:
        form_action = re.findall(r'form.*?action="([^"]+login)"', resp.content)[0]
        form = re.findall(r'(?sim)form.*?action="[^"]+login"[^>]*>(.*?)</form>', resp.content)[0]
    except (StandardError, Exception):
        print('Issue finding form action url, check html for updates')
        continue

    inputs = re.findall(r'(?is)(<input.*?name="[^"]+".*?>)', form)
    pairs = [(tup[0]) for tup in [re.findall(r'(?is)name="([^"]+)"(?:.*?value="([^"]+)")?', x) for x in inputs]]
    params = {}
    filled = 0
    for name, value in pairs:
        if 'username' == name:
            params[name] = username
            filled += 1
        elif 'password' == name:
            params[name] = userdata['password']
            filled += 1
        else:
            params[name] = value
    if 2 != filled:
        print('Issue filling in form, fields not found, check html for updates')
        continue

    url = form_action
    print('POSTing Rooster login form')
    try:
        sleep_random()
        resp = req.one(session.prepare_request(
            requests.Request('POST', url, data=params)))
        if abort:
            break
    except (StandardError, Exception):
        resp = None
    if not resp:
        print('Issue with response from login to site, aborting')
        continue
    try:
        username = re.findall('(?sim)user/(.*?)">My Profile', resp.content)[0]
    except IndexError:
        print('Login failed')
        continue

    episodes = []
    url_q = []
    showname_maps = {}
    for url in urls:
        showname = None
        if isinstance(url, dict):
            showname, url = tuple(url.items())[0]

        if not re.search('/(season|episode)/', url):
            print('Url must contain \'/season/\' or \'/episode/\': %s' % url)
            continue

        if None is not showname:
            showname_maps[urlkey(url)] = showname

        if re.search('/episode/', url):
            episodes += [url]
        else:
            url_q += [url]

    for resp in req.swarm(url_q, maintainOrder=False):
        if abort:
            req.stop()
            break

        season_block = ''
        try:
            season_block = re.findall('(?sim)grid-blocks.*begin\sfooter', resp.content)[0]
        except (StandardError, Exception):
            pass

        showname = showname_maps.get(urlkey(resp.request.url))
        for ep_block in re.findall('(?sim)<li>.*?post-stamp[^<]+</p>', season_block):
            if re.findall('(?sim)ion-star', ep_block):
                num_member_access += 1
                if free_access_only:
                    continue
            for ep in re.findall('href="(https?://roosterteeth.com/episode/.*?)"', ep_block):
                if ep not in episodes:
                    episodes += [ep]

                if None is not showname:
                    showname_maps[urlkey(ep)] = showname

    # parse url into usable fragments (where x=season num and y=episode num) from...
    #  show_name-x-y
    #  show_name-season-x-y
    #  show_name-season-x-y
    #  show_name-volume-x-y
    #  show_name-volume-x-y
    #  show_name-season-x-episode-y
    #  show_name-season-x-chapter-y
    #  show_name-volume-x-episode-y
    #  show_name-volume-x-chapter-y
    # Otherwise treat as Special
    meta = {}
    log_lists = {}
    for url in episodes:
        show_name, season, episode, ep_path, log_path = 5 * [None]
        try:
            show_name_parts = re.findall('episode/([^"]+?)[-](.*)', url)[0]
            show_name, remaining1 = show_name_parts[0], show_name_parts[1]
            show_name = showname_maps.get(urlkey(url), show_name)

            if re.search('(?i)^(?:[a-z]:[\\]|[/])', show_parent):
                ep_path = os.path.join(os.path.realpath(show_parent), show_name)
            else:
                ep_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), show_parent, show_name)
            log_path = os.path.join(ep_path, '_log')

            season_parts = re.findall('(?:season-|volume-)?(\d+|20\d\d)(.*)', remaining1)[0]
            season, remaining2 = season_parts[0], season_parts[1]
            try:
                # remove erroneous duplication before further parsing
                remaining2 = re.findall('.*(?:season-|volume-)(\d+|20\d\d)(.*)', remaining2)[0][1]
            except IndexError:
                pass

            episode = re.findall('^-(?:episode-|chapter-)?(\d+)', remaining2)[0]

            season = '%02d' % int(season)
            episode = '%02d' % int(episode)
            season_dir = season_template % (dict(season_number=season))
            log_path = os.path.join(log_path, season_dir)
            ep_path = os.path.join(ep_path, season_dir)
            ep_name = ep_template % (dict(show_name=show_name, season=season, episode=episode))

        except IndexError:
            if ep_path:
                log_path = os.path.join(log_path, 'Specials')
                ep_path = os.path.join(ep_path, 'Specials')
                ep_name = url.rsplit('/', 1)[-1]

        if show_name and ep_path:

            # only add url to fetch meta where episode file does not already exist in _filelist.txt
            log_file = os.path.join(log_path, '_filelist.txt')
            log_key = urlkey(log_file)
            if log_key not in log_lists:
                file_list = []
                if os.path.exists(log_file):
                    with open(log_file, 'r') as rh:
                        file_list = rh.readlines()
                    file_list = [x.strip() for x in file_list]
                log_lists[log_key] = dict(log_file=log_file, file_list=file_list[:], dedupe_list=file_list)

            full_name = os.path.join(ep_path, '%s.ext' % ep_name)
            if full_name not in log_lists[log_key].get('dedupe_list'):
                log_lists[log_key]['dedupe_list'] += [full_name]

                meta[urlkey(url)] = dict(show_name=show_name, season=season, episode=episode,
                                         ep_name=ep_name, ep_ext=ep_ext, ep_path=ep_path, ep_url=url,
                                         log_key=log_key, log_name=full_name)

    num_snatch = (len(meta), test_num_snatch)[bool(test_mode)]
    print('Attempting to fetch %s episode(s)...' % num_snatch)
    for n, url in enumerate(filter(lambda ep_url: urlkey(ep_url) in meta, episodes)):
        if abort or (test_mode and n == num_snatch):
            break

        print('Episode page: %s' % url)
        try:
            sleep_random()
            resp = req.one(url)
        except (StandardError, Exception):
            continue

        if abort:
            break

        if resp:
            if resp.ok:
                try:
                    meta_url_m3u8 = re.findall('file:.*?["\']([^"\']+)', resp.content)[0]
                except IndexError:
                    continue
                if ep_append_title:
                    try:
                        meta_title = re.findall('videoTitle:.*?["\'](.*)\'', resp.content)[0]

                        # strip out any bad chars
                        for c in bad_chars:
                            meta_title = meta_title.replace(c, '')

                        title_parts = re.split('-', meta_title)
                        if 1 < len(title_parts):
                            meta[urlkey(url)]['ep_name'] += ep_append_title % dict(
                                title=' - '.join([tp.strip() for tp in title_parts]),
                                title_last_part=title_parts[-1].strip())
                    except IndexError:
                        pass
            else:
                print('Error response contains code:%s with short reason:%s' % (resp.status_code, resp.reason))
                continue
        else:
            print('Error no data returned from server, check the site in a browser')
            continue

        print('Fetching episode meta...')
        try:
            sleep_random()
            index_m3u8 = req.one(meta_url_m3u8)
        except (StandardError, Exception):
            continue
        if abort:
            break

        try:
            options = re.findall('(?im)^.*(?:resolution=(\d+)x(\d+)).*[\r\n]+(.*)$', index_m3u8.content)
        except (StandardError, Exception):
            options = []
        if not options:
            print('m3u8 response has no resolution to pick best from, skipping episode: %s' % url)
            continue

        options = [(int(res_x), int(res_y), m3u8_url) for (res_x, res_y, m3u8_url) in options]
        options.sort(key=lambda tu: tu[0], reverse=True)

        base_url = meta_url_m3u8.rsplit('/', 1)[0]

        pick = 0
        video_urls = []
        # if iteration fails clear video_urls to fallback to next res
        while pick != len(options) and not video_urls:
            res = '%s x %s' % (options[pick][0], options[pick][1])
            res_file_name = re.search('(72|108|216)0', str(options[pick][1])) and '.%sp' % options[pick][1] or ''

            sleep_random()
            try:
                pick_url = options[pick][2]
                data_m3u8 = req.one(('%s/%s' % (base_url, pick_url), pick_url)[pick_url.startswith('http')])
            except (StandardError, Exception):
                pick += 1
                continue
            if abort:
                break

            for v in re.findall('(?im)#EXTINF:.*?[\r\n]+(.*?)$', data_m3u8.content):
                if v.startswith('http'):
                    video_urls += [v]
                else:
                    v = v.lstrip('/')
                    vid_name = '%s/%s' % (pick_url.rsplit('/', 1)[0], v)
                    if not v.startswith('/') and pick_url.startswith('http'):
                        video_urls += [vid_name]
                    elif not v.startswith('/') and '/' in pick_url:
                        video_urls += ['%s/%s' % (base_url, vid_name)]
                    else:
                        video_urls += ['%s/%s' % (base_url, v)]

            pick += 1

            if not video_urls:
                continue

            if re.search('(?i)\.mp4.*?\.ts$', video_urls[-1]):
                meta[urlkey(url)]['ep_ext'] = '.mp4'

            print('Show name: %s .. Episode: %s' % (meta[urlkey(url)]['show_name'], meta[urlkey(url)]['ep_name']))
            print('Save path: %s' % (meta[urlkey(url)]['ep_path']))
            print('Fetching %s parts(s) for %s resolution %s' % (
                (len(video_urls), '%s/%s (test mode)' % (num_snatch, len(video_urls)))[bool(test_mode)],
                meta[urlkey(url)]['ep_ext'], res))
            saved = []
            _print('Parts: ')
            url_q = []
            for video_url in video_urls:
                if test_mode and num_snatch == len(saved):
                    break

                if abort:
                    break

                # skip over already saved intermediate files
                path_name = os.path.join(temp_files, video_url.rsplit('/', 1)[-1])
                if os.path.exists(path_name):
                    saved += [path_name]
                    _print('# ')
                    continue

                url_q += [video_url]

            save_order = [os.path.join(temp_files, uq.rsplit('/', 1)[-1]) for uq in url_q]
            progress = 0
            printed_done = []
            url_cnt = len(url_q)
            while not abort:
                working_q = [url_q.pop(0) for x in range(0, concurrent_fetches) if x < len(url_q)]
                if not working_q:
                    break

                try:
                    for data in req.swarm(working_q, maintainOrder=False, responsePreprocessor=RespProcessor()):
                        progress += 1
                        done = int(float(progress)/url_cnt * 100)
                        if done in (5, 20, 40, 60, 80, 95) and done not in printed_done:
                            printed_done += [done]
                            _print('%d%% ' % done)
                        else:
                            _print('# ')

                        if abort:
                            req.stop()

                        if data:
                            if data.ok:
                                saved += [os.path.join(temp_files, data.request.url.rsplit('/', 1)[-1])]
                                if test_mode and len(saved) >= num_snatch:
                                    req.stop()
                                    abort = True
                                    break
                                continue
                            else:
                                print('Error response contains code:%s with short reason:%s' % (
                                    data.status_code, data.reason))

                        else:
                            print('Error no data returned from server, check the site in a browser')

                        if not abort:
                            if saved:
                                print('Cleaning up and removing redundant files for resolution %s' % res)
                                remove(saved)
                                saved = []
                            break
                except (StandardError, Exception):
                    print('Cleaning up and removing redundant files for resolution %s' % res)
                    remove(saved)
                    saved = []

                if not saved:
                    break
            print(' ')

            if not saved:
                video_urls = []  # attempt next best resolution
                continue

            file_name = '%s%s' % (meta[urlkey(url)]['ep_name'], '.txt')
            ffmpeg_list = os.path.join(temp_files, file_name)
            try:
                with open(ffmpeg_list, 'wb') as f:
                    f.write('file \'%s\'' % '\'\r\nfile \''.join([os.path.basename(s)
                                                                  for s in save_order if s in saved]))
            except OSError:
                print('Error saving: %s' % ffmpeg_list)
                print('Cleaning up and removing redundant files for resolution %s' % res)
                remove(saved)
                video_urls = []  # attempt next best resolution
                continue

            final_name = '%s%s.WEBRip%s' % (
                (meta[urlkey(url)]['ep_name']), res_file_name, meta[urlkey(url)]['ep_ext'])
            cmd = [ffmpeg_bin, '-f', 'concat', '-safe', '0', '-i', ffmpeg_list, '-c', 'copy',
                   '-bsf:a', 'aac_adtstoasc', '-y', os.path.join(meta[urlkey(url)]['ep_path'], final_name)]
            ffmpeg_buffer = subprocess.Popen(cmd, cwd=temp_files,
                                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT).communicate()
            try:
                result = re.findall('(video:\s*[^\s]+\saudio:\s*[^\s]+).*?muxing overhead', ffmpeg_buffer[0])[0]
                print('Saved: %s %s' % (final_name, result))
                remove(saved + [ffmpeg_list])

                # ensure the log dir can be created
                log_meta = log_lists[meta[urlkey(url)]['log_key']]
                log_path = os.path.split(log_meta['log_file'])[0]
                if not os.access(log_path, os.F_OK):
                    try:
                        os.makedirs(log_path, 0o744)
                    except os.error:
                        print(u'Unable to create dir: %s' % log_path)

                log_meta['file_list'] += [meta[urlkey(url)]['log_name']]
                with open(log_meta['log_file'], 'wb') as wh:
                    wh.write('\r\n'.join(log_meta['file_list']))

                num_saved += 1
            except (StandardError, Exception):
                remove(saved + [ffmpeg_list, os.path.join(meta[urlkey(url)]['ep_path'], final_name)])
                video_urls = []  # attempt next best resolution
                print('Error: %s\r\n' % '\r\n'.join([line for line in ffmpeg_buffer[0].strip().split('\r\n')
                                                     if not re.search('^\s*(built|config|lib)', line)]))
                continue

    print('---')
    print('Success. Saved %s/%s episodes %s %s member only access. (%.2f secs).' % (
        num_saved, len(episodes), ('with', 'skipping')[free_access_only], num_member_access,
        (time.time() - start) - slept))

    num_creds -= 1
    if num_creds:
        del req
        print('---')
        sleep_random()

if not client_creds:
    print('No username/password added to settings.py, aborting')

if changed:
    save_userlist()

print('----------------------------')
print('Done.')
