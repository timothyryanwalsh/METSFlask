from flask import Flask, request, redirect, render_template
from werkzeug.utils import secure_filename

import collections
import fnmatch
import math
import os
import sys
from lxml import etree, objectify

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = set(['xml'])

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def convert_size(size):
    # convert size to human-readable form
    size = int(size)
    size_name = ("bytes", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = int(math.floor(math.log(size,1024)))
    p = math.pow(1024,i)
    s = round(size/p)
    s = str(s)
    s = s.replace('.0', '')
    return '%s %s' % (s,size_name[i])

def mets_to_list_of_dicts(mets_path):
    # create list
    original_files = []

    # open xml file and strip namespaces
    tree = etree.parse(mets_path)
    root = tree.getroot()

    # strip namespaces from XML
    for elem in root.getiterator():
        if not hasattr(elem.tag, 'find'): continue  # (1)
        i = elem.tag.find('}')
        if i >= 0:
            elem.tag = elem.tag[i+1:]
    objectify.deannotate(root, cleanup_namespaces=True)

    # store names and xpaths of desired info from individual files in tuples and convert to ordered dict
    xml_file_elements = (('filepath', './techMD/mdWrap/xmlData/object/originalName'),
                    ('uuid', './techMD/mdWrap/xmlData/object/objectIdentifier/objectIdentifierValue'), 
                    ('sha256', './techMD/mdWrap/xmlData/object/objectCharacteristics/fixity/messageDigest'), 
                    ('bytes', './techMD/mdWrap/xmlData/object/objectCharacteristics/size'), 
                    ('format', './techMD/mdWrap/xmlData/object/objectCharacteristics/format/formatDesignation/formatName'), 
                    ('version', './techMD/mdWrap/xmlData/object/objectCharacteristics/format/formatDesignation/formatVersion'), 
                    ('puid', './techMD/mdWrap/xmlData/object/objectCharacteristics/format/formatRegistry/formatRegistryKey'), 
                    ('fits_modified', './techMD/mdWrap/xmlData/object/objectCharacteristics/objectCharacteristicsExtension/fits/toolOutput/tool[@name="Exiftool"]/exiftool/FileModifyDate'), 
                    ('fits_created', './techMD/mdWrap/xmlData/object/objectCharacteristics/objectCharacteristicsExtension/fits/fileinfo/created[@toolname="Exiftool"]'), 
                    ('fileutil_mimetype', './techMD/mdWrap/xmlData/object/objectCharacteristics/objectCharacteristicsExtension/fits/toolOutput/tool[@name="file utility"]/fileUtilityOutput/mimetype'), 
                    ('fileutil_format', './techMD/mdWrap/xmlData/object/objectCharacteristics/objectCharacteristicsExtension/fits/toolOutput/tool[@name="file utility"]/fileUtilityOutput/format'), 
                    ('exiftool_mimetype', './techMD/mdWrap/xmlData/object/objectCharacteristics/objectCharacteristicsExtension/RDF/Description/MIMEType'), 
                    ('exiftool_format', './techMD/mdWrap/xmlData/object/objectCharacteristics/objectCharacteristicsExtension/RDF/Description/FileType'), 
                    ('mediainfo_modified', './techMD/mdWrap/xmlData/object/objectCharacteristics/objectCharacteristicsExtension/Mediainfo/File/track[@type="General"]/File_last_modification_date__local_'), 
                    ('mediainfo_mimetype', './techMD/mdWrap/xmlData/object/objectCharacteristics/objectCharacteristicsExtension/Mediainfo/File/track[@type="General"]/Internet_media_type'), 
                    ('mediainfo_format', './techMD/mdWrap/xmlData/object/objectCharacteristics/objectCharacteristicsExtension/Mediainfo/File/track[@type="General"]/Format'))
    xml_file_elements = collections.OrderedDict(xml_file_elements)

    # build xml document root
    mets_root = root

    # gather info for each file in filegroup "original" and write to files.csv
    for target in mets_root.findall(".//fileGrp[@USE='original']/file"):
            
        # create new dictionary for this item's info
        file_data = {}

        # create new list of dicts for premis events in file_data
        file_data['premis_events'] = []

        # gather amdsec id from filesec
        amdsec_id = target.attrib['ADMID']
        file_data['amdsec_id'] = amdsec_id
            
        # parse each amdSec 
        amdsec_xpath = ".//amdSec[@ID='%s']" % (amdsec_id)
        for target1 in mets_root.findall(amdsec_xpath):
            
            # iterate over elements and write key, value for each to file_data dictionary
            for key, value in xml_file_elements.items():
                try:
                    file_data['%s' % (key)] = target1.find(value).text
                except AttributeError:
                    file_data['%s' % (key)] = ''

            # parse info for each PREMIS event associated with amdSec
            premis_event_xpath = ".//digiprovMD/mdWrap[@MDTYPE='PREMIS:EVENT']"
            for target2 in target1.findall(premis_event_xpath):

                # create dict to store data
                premis_event = {}

                # create dict for names and xpaths of desired elements
                premis_key_values = {
                    'event_uuid': './xmlData/event/eventIdentifier/eventIdentifierValue', 
                    'event_type': './xmlData/event/eventType', 
                    'event_datetime': './xmlData/event/eventDateTime', 
                    'event_outcome': './xmlData/event/eventOutcomeInformation/eventOutcome', 
                    'event_detail': './xmlData/event/eventOutcomeInformation/eventOutcomeDetail/eventOutcomeDetailNote' 
                }

                # iterate over elements and write key, value for each to premis_event dictionary
                for key, value in premis_key_values.items():
                    try:
                        premis_event['%s' % (key)] = target2.find(value).text
                    except AttributeError:
                        premis_event['%s' % (key)] = ''

                # write premis_event dict to file_data
                file_data['premis_events'].append(premis_event)


        # format filepath
        file_data['filepath'] = file_data['filepath'].replace('%transferDirectory%', '')

        # format PUID
        file_data['puid'] = "<a href=\"http://nationalarchives.gov.uk/PRONOM/%s\" target=\"_blank\">%s</a>" % (file_data['puid'], file_data['puid'])

        # create human-readable size
        file_data['size'] = convert_size(file_data['bytes'])

        # add file_data to list
        original_files.append(file_data)


    return original_files

original_files = []

@app.route("/", methods=['GET', 'POST'])
def index():
    return render_template('upload.html')


@app.route('/mets-view', methods = ['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        # check if the post request has the file part
        if 'file' not in request.files:
            flash('No file part')
            return render_template('upload.html')
        file = request.files['file']
        # if user does not select file, browser also
        # submit a empty part without filename
        if file.filename == '':
            flash('No selected file')
            return render_template('upload.html')
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            mets_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            global original_files
            original_files = mets_to_list_of_dicts(mets_path)
            return render_template('originalfiles.html', original_files = original_files)


@app.route('/file/<UUID>')
def show_file(UUID):
    for original_file in original_files:
        if original_file["uuid"] == UUID:
            target_original_file = original_file
            break
    return render_template('detail.html', original_file=target_original_file)
