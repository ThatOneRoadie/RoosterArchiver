import os
# ===========================================================================================
# RoosterTeeth fetcher settings
# ===========================================================================================
# username, password tuples
#
# Example, comma seperated accounts
#
# client_creds = [
#        ('account_email', 'password'),
#        ('account_email2', 'password2'),
#        ('account_email3', 'password3')
# ]

client_creds = [
    ('account_email', 'password')
]

# In case this ever changes
site_url = 'https://roosterteeth.com'

# Normally True, set free_access_only False to also fetch FIRST* members only page content
# if you cannot access star marked videos on the site, then leave this as True to reduce fetch process time
free_access_only = True

# A mix of one or more episode or season url(s) to fetch (each url *must* contain either '/episode/' or '/season/')
#
#  Example, comma separated addresses copied from a browser...
#  Tip: can override what is used for showname by using for an entry {'show_name': URL}
#
# urls = [
#     {'RWBY': 'http://roosterteeth.com/show/rwby/season/rwby-volume-5'},
#     'http://roosterteeth.com/episode/always-open-2017-25-7-fg397t',
#     'http://roosterteeth.com/episode/rt-podcast-2017-466-ghhgo5h',
#     'http://roosterteeth.com/show/rt-podcast/season/rt-podcast-2017',
# ]
urls = [
]

# Normally False, set paranoid_mode True to add a random pause between each access to the server
paranoid_mode = False

# Normally False, set test_mode True to only fetch the first 3 sections of an episode
test_mode = True

# Numeric limit for fetching when test mode is True
test_num_snatch = 3

# Path to ffmpeg executable, normally in <app_path>/bin
ffmpeg_bin = os.path.join(
    os.path.realpath(os.path.dirname(__file__)), 'bin', 'ffmpeg')

# Default output format for ffmpeg
ep_ext = '.mkv'

# Episode path where to move completed downloads (absolute full path, or relative to <path/to/rooster>)
show_parent = '_rooster_shows'

# Path where to build downloaded episode parts (absolute full path, or relative to <path/to/rooster>)
temp_files = '_rooster_tmp'

# Episode file naming template
#
#  Examples of baseline file naming pattern
#
#  ep_template = '%(show_name)s - S%(season)sE%(episode)s'
#  ep_template = '%(show_name)s.S%(season)sE%(episode)s'  # Default
ep_template = '%(show_name)s.S%(season)sE%(episode)s'

# Template to append only everything after the final hyphen in the name, ignoring &ndash;
#  ep_append_title = ' - %(title_part)s'
#  ep_append_title = '.%(title_part)s'
#
#  Template to append everything found as title
#  ep_append_title = ' - %(title)s'
#  ep_append_title = '.%(title)s'
#
#  Set False to not append anything
#  ep_append_title = False
ep_append_title = '.%(title_last_part)s'

# Template for season folder
#  season_template = 'Season %(season_number)s'
season_template = 'Season %(season_number)s'

# Chars in this list are stripped from save names to prevent fs issues
#  bad_chars = u':\u2019'
bad_chars = u':\u2019'
