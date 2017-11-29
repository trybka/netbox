"""S2 Netbox API."""
from itertools import groupby
import copy
import csv
import urllib2
import xml.dom.minidom
import xml.etree.ElementTree as ElementTree
import yaml

# Some helpful constants.
CMD = 'COMMAND'
NB_API = 'NETBOX-API'
TEMPLATE_REQUEST = {NB_API: {CMD: {'num': '1'}}}
TXT = '__text__'
GETAPIVERSION = {NB_API: {CMD: {'num': '1', 'name': 'GetAPIVersion'}}}

# Convenience rename for some code I copypasta'd.
etree = ElementTree


def GetConfig(filename):
  config = {}
  with open(filename) as yaml_file:
    config = yaml.load(yaml_file)
  return config


# Yes, this is gross.
CONFIG = GetConfig('s2.yaml')


def xml2d(e):
  """Convert an etree into a dict structure.

  @type  e: etree.Element
  @param e: the root of the tree
  @return: The dictionary representation of the XML tree

  """
  def _xml2d(e):
    kids = dict(e.attrib)
    if e.text:
      kids['__text__'] = e.text
    if e.tail:
      kids['__tail__'] = e.tail
    for k, g in groupby(e, lambda x: x.tag):
      g = [_xml2d(x) for x in g]
      kids[k] = g
    return kids
  return {e.tag: _xml2d(e)}


def d2xml(d):
  """convert dict to xml.

     1. The top level d must contain a single entry i.e. the root element
     2.  Keys of the dictionary become sublements or attributes
     3.  If a value is a simple string, then the key is an attribute
     4.  if a value is dict then, then key is a subelement
     5.  if a value is list, then key is a set of sublements

     a  = { 'module' : {'tag' : [ { 'name': 'a', 'value': 'b'},
                                  { 'name': 'c', 'value': 'd'},
                               ],
                        'gobject' : { 'name': 'g', 'type':'xx' },
                        'uri' : 'test',
                     }
         }
  >>> d2xml(a)
  <module uri="test">
     <gobject type="xx" name="g"/>
     <tag name="a" value="b"/>
     <tag name="c" value="d"/>
  </module>

  @type  d: dict 
  @param d: A dictionary formatted as an XML document
  @return:  A etree Root element

  """
  def _d2xml(d, p):
    for k, v in d.items():
      if isinstance(v, dict):
        node = etree.SubElement(p, k)
        _d2xml(v, node)
      elif isinstance(v, list):
        for item in v:
          node = etree.SubElement(p, k)
          _d2xml(item, node)
      elif k == '__text__':
        p.text = v
      elif k == '__tail__':
        p.tail = v
      else:
        p.set(k, v)

  k, v = d.items()[0]
  node = etree.Element(k)
  _d2xml(v, node)
  return node


def post(url, data, contenttype):
  """Sends a POST request to the given URL with the given data and content-
  type."""
  request = urllib2.Request(url, data)
  request.add_header('Content-Type', contenttype)
  response = urllib2.urlopen(request)
  return response.read()


def postxml(url, elem):
  """Sends a POST request to the URL with the XML rooted at 'elem' as
  data."""
  data = ElementTree.tostring(elem, encoding='UTF-8')
  return post(url, data, 'text/xml')


def get_search(lastname=None, firstname=None, nextkey=None):
  search_params = {}
  if lastname is not None:
    search_params['LASTNAME'] = lastname
  if firstname is not None:
    search_params['FIRSTNAME'] = firstname
  if nextkey:
    search_params['STARTFROMKEY'] = str(nextkey)
  return get_cmd(name='SearchPersonData', params=search_params)


def remove_access(personid=None, cardid=None):
  search_params = {'accesslevels': [('accesslevel', CONFIG['no_access'])]}
  cred_params = {'cardformat': CONFIG['card_format']}
  if personid is not None:
    search_params['personid'] = personid
    if cardid is not None:
      cred_params['personid'] = personid
      cred_params['encodednum'] = cardid
      execute(get_cmd('RemoveCredential', cred_params))
    execute(get_cmd('ModifyPerson', search_params))


def add_person(lastname=None, firstname=None):
  search_params = {'accesslevels': [('accesslevel', CONFIG['all_access'])]}
  if lastname is not None:
    search_params['LASTNAME'] = lastname
  if firstname is not None:
    search_params['FIRSTNAME'] = firstname
  return get_cmd(name='AddPerson', params=search_params)


def add_cred(personid=None, cardid=None):
  cred_params = {'cardformat': CONFIG['card_format']}
  if personid is not None:
    cred_params['personid'] = personid
  if cardid is not None:
    cred_params['encodednum'] = cardid
  return get_cmd(name='AddCredential', params=cred_params)


def get_cmd(name=None, params=None):
  """Create a command with the given name and params.

  Args:
    name: str, the name of the command to run.
    params: dict, a dict of the params to send.

  Returns:
    dict, with the correct wrapping to be properly parsed into XML.

  """
  new_params = {}
  for k, v in params.iteritems():
    if type(v) is str:
      new_params[k.upper()] = {TXT: v}
    elif type(v) is list:
      l = []
      for t in v:
        l.append({t[0].upper(): {TXT: t[1]}})
      new_params[k.upper()] = l

  request = copy.deepcopy(TEMPLATE_REQUEST)
  command = request[NB_API][CMD]
  command['name'] = name
  command['PARAMS'] = new_params

  return request


def pretty_print(xml_string):
  """Handy method for debugging XML.

  Args:
    xml_string: str, the XML as a string

  Returns:
    str, XML formatted with tabs and newlines and such.

  """
  parsed = xml.dom.minidom.parseString(xml_string)
  pretty_xml_as_string = parsed.toprettyxml()
  return pretty_xml_as_string


def execute(command):
  """Convenience method to execute a command.

  Converts the response to a dict, and strips the extraneous layers off.

  Args:
    command: A dict with all the require fields (see get_cmd).

  Returns:
    dict, parsed XML converted to a dictionary with the API wrapper stripped.

  """
  return xml2d(etree.XML(postxml(CONFIG['url'], d2xml(command))))['NETBOX']['RESPONSE']


def get_key(obj, key):
  """Convenience function to get a given key out of a returned obj.

  The API has all these annoying layers of indirection. Tries to decode that.

  Args:
    obj: The dictionary, probably a response.
    key: The key to return.
  Returns:
    The value, after a few layers of indirection.

  """
  val = obj[key][0]
  if type(val) == dict and val.has_key(TXT):
    return val[TXT]
  else:
    return val


def successful(resp):
  """Determines if a response is successful."""
  return resp['CODE'][0]['__text__'] == 'SUCCESS'


def add_new_members(fname):
  people = {}
  with open(fname) as f:
    cf = csv.DictReader(f)
    for person in cf:
      people[person['last']] = person

  for person in people.itervalues():
    response = execute(add_person(person['last'], person['first']))
    response = response[0]
    if successful(response):
      person['pid'] = response['DETAILS'][0]['PERSONID'][0][TXT]
      response = execute(add_cred(person['pid'], person['card_id']))[0]
      if not successful(response):
        print response
    else:
      print response


def get_people(resp):
  """Returns a list."""
  return get_key(get_key(resp, 'DETAILS'), 'PEOPLE')


def has_access(person):
  key_active = get_key(person, 'ACCESSLEVELS')
  return 'ACCESSLEVEL' in key_active and get_key(key_active, 'ACCESSLEVEL') == CONFIG['all_access']


def do_audit():
  people = {}
  with open('roster.csv') as f:
    cf = csv.DictReader(f)
    for person in cf:
      people[person['last']] = person

  to_process = []
  nextkey = None
  while nextkey != '-1':
    response = execute(get_search(nextkey=nextkey))[0]
    # Don't use get_key here.
    to_process.extend(get_people(response)['PERSON'])
    nextkey = get_key(get_key(response, 'DETAILS'), 'NEXTKEY')
  for person in to_process:
    if has_access(person) and get_key(person, 'LASTNAME') not in people:
      print '%s,%s' % (get_key(person, 'LASTNAME'), get_key(person, 'FIRSTNAME'))


if __name__ == '__main__':
  # By default, add new members
  # add_new_members('new2019.csv')
  do_audit()
