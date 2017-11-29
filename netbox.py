"""S2 Netbox API."""
from itertools import groupby
import copy
import csv
import urllib2
import yaml
import xmltodict
import traceback, sys, code

# Some helpful constants.
CMD = 'COMMAND'
NB_API = 'NETBOX-API'
TEMPLATE_REQUEST = {NB_API: {CMD: {'@num': '1'}}}
GETAPIVERSION = {NB_API: {CMD: {'@num': '1', '@name': 'GetAPIVersion'}}}


def GetConfig(filename):
  config = {}
  with open(filename) as yaml_file:
    config = yaml.load(yaml_file)
  return config


# Yes, this is gross.
CONFIG = GetConfig('s2.yaml')


def post(url, data, contenttype):
  """Sends a POST request to the given URL."""
  request = urllib2.Request(url, data)
  request.add_header('Content-Type', contenttype)
  response = urllib2.urlopen(request)
  return response.read()


def get_search(lastname=None, firstname=None, nextkey=None):
  """Constructs a SearchPersonData request."""
  search_params = {}
  if lastname is not None:
    search_params['LASTNAME'] = lastname
  if firstname is not None:
    search_params['FIRSTNAME'] = firstname
  if nextkey:
    search_params['STARTFROMKEY'] = str(nextkey)
  return get_cmd(name='SearchPersonData', params=search_params)


def remove_access(personid=None, cardid=None):
  """Removes access for the given personid, and optionally one of their cards."""
  # Note, we actually set their access to 'None' instead of removing.
  # The API does not actually support removal of access from a person.
  search_params = {'ACCESSLEVELS': [{'ACCESSLEVEL': CONFIG['no_access']}]}
  cred_params = {'CARDFORMAT': CONFIG['card_format']}
  if personid is not None:
    search_params['PERSONID'] = personid
    if cardid is not None:
      cred_params['PERSONID'] = personid
      cred_params['ENCODEDNUM'] = cardid
      execute(get_cmd('RemoveCredential', cred_params))
    execute(get_cmd('ModifyPerson', search_params))


def add_person(lastname=None, firstname=None):
  """Adds a new person with full access."""
  search_params = {'ACCESSLEVELS': [{'ACCESSLEVEL': CONFIG['all_access']}]}
  if lastname is not None:
    search_params['LASTNAME'] = lastname
  if firstname is not None:
    search_params['FIRSTNAME'] = firstname
  return get_cmd(name='AddPerson', params=search_params)


def add_cred(personid=None, cardid=None):
  cred_params = {'CARDFORMAT': CONFIG['card_format']}
  if personid is not None:
    cred_params['PERSONID'] = personid
  if cardid is not None:
    cred_params['ENCODEDNUM'] = cardid
  return get_cmd(name='AddCredential', params=cred_params)


def get_cmd(name=None, params=None):
  """Create a command with the given name and params.

  Args:
    name: str, the name of the command to run.
    params: dict, a dict of the params to send.

  Returns:
    dict, with the correct wrapping to be properly parsed into XML.

  """
  request = copy.deepcopy(TEMPLATE_REQUEST)
  command = request[NB_API][CMD]
  command['@name'] = name
  command['PARAMS'] = params
  return request


def execute(command):
  """Convenience method to execute a command.

  Converts the response to a dict, and strips the extraneous layers off.

  Args:
    command: A dict with all the require fields (see get_cmd).

  Returns:
    dict, parsed XML converted to a dictionary with the API wrapper stripped.

  """
  xml_resp = xmltodict.parse(post(CONFIG['url'], xmltodict.unparse(command), 'text/xml'))
  return xml_resp['NETBOX']['RESPONSE']


def successful(resp):
  """Determines if a response is successful."""
  return resp['CODE'] == 'SUCCESS'


def add_new_members(fname):
  people = {}
  with open(fname) as f:
    cf = csv.DictReader(f)
    for person in cf:
      people[person['last']] = person

  for person in people.itervalues():
    response = execute(add_person(person['last'], person['first']))
    if successful(response):
      person['pid'] = response['DETAILS']['PERSONID']
      response = execute(add_cred(person['pid'], person['card_id']))
      if not successful(response):
        print response
    else:
      print response


def get_people(resp):
  """Returns a list."""
  return resp['DETAILS']['PEOPLE']


def has_access(person):
  key_active = person['ACCESSLEVELS']
  return key_active and 'ACCESSLEVEL' in key_active and key_active['ACCESSLEVEL'] == CONFIG['all_access']


def do_audit():
  people = {}
  with open('roster.csv') as f:
    cf = csv.DictReader(f)
    for person in cf:
      people[person['last']] = person

  to_process = []
  nextkey = None
  while nextkey != '-1':
    response = execute(get_search(nextkey=nextkey))
    to_process.extend(get_people(response)['PERSON'])
    nextkey = response['DETAILS']['NEXTKEY']
  for person in to_process:
    if has_access(person) and person['LASTNAME'] not in people:
      print '%s,%s' % (person['LASTNAME'], person['FIRSTNAME'])


if __name__ == '__main__':
  try:  
    # By default, add new members
    # add_new_members('new2019.csv')
    do_audit()
  except:
    # Cool exeception handling from https://stackoverflow.com/a/242514
    type, value, tb = sys.exc_info()
    traceback.print_exc()
    last_frame = lambda tb=tb: last_frame(tb.tb_next) if tb.tb_next else tb
    frame = last_frame().tb_frame
    ns = dict(frame.f_globals)
    ns.update(frame.f_locals)
    code.interact(local=ns)
