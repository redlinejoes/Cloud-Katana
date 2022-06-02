from inspect import Parameter
from sqlite3 import paramstyle
import nbformat as nbf
import glob
from numpy import kaiser
from sqlalchemy import false, true
import yaml
import os
import json
import copy
from jinja2 import Template
import uuid
import jupytext

###### Variables #####
current_directory = os.path.dirname(__file__)
app_directory = os.path.join(current_directory, "../..", "functionapp")
templates_directory = os.path.join(current_directory, "../templates")
metadata_directory = os.path.join(current_directory, "../../simulations/atomic")
docs_directory = os.path.join(current_directory, "../../docs")
simulations_directory = os.path.join(docs_directory, "simulate")
metadata_files = os.path.join(metadata_directory, "**/", "*.yml")
toc_file = os.path.join(docs_directory, "_toc.yml")
summary_table_template = os.path.join(templates_directory, "summary_template.md")
toc_template = os.path.join(templates_directory, "toc_template.json")
pwsh_req_template = os.path.join(templates_directory, "pwsh-requirements.jinja2")
notebooks_config_path = os.path.join(current_directory, "../notebooks/_config.yml")

##### Tactic Mappings #####
tactic_maps = {
    "TA0001" : "initial_access",
    "TA0002" : "execution",
    "TA0003" : "persistence",
    "TA0004" : "privilege_escalation",
    "TA0005" : "defense_evasion",
    "TA0006" : "credential_access",
    "TA0007" : "discovery",
    "TA0008" : "lateral_movement",
    "TA0009" : "collection",
    "TA0011" : "command_and_control",
    "TA0010" : "exfiltration",
    "TA0040" : "impact",
    "TA0043" : "reconnaissance",
    "TA0042" : "resource_development"
}

##### Analytic Summary #####
summary_table = [
    {
        "platform" : "Windows",
        "action" : [],
        "tactics" : []
    },
    {
        "platform" : "Azure",
        "action" : [],
        "tactics" : []
    },
    {
        "platform" : "AWS",
        "action" : [],
        "tactics" : []
    }
]

##### Platform Mappings
platform_maps = {
    'Azure' : 'Azure',
    'WindowsHybridWorker' : 'Windows'
}

##### Mapping of Azure Function Activity
activity_function_maps = {
    'Azure' : 'AzureActivity',
    'WindowsHybridWorker' : 'WindHybridWorkerActivity'
}

##### Open attacker actions yaml file available #####
print("[+] Opening attack actions yaml files..")
actions_list = glob.glob(metadata_files)
actions_loaded = []
for action in actions_list:
    print(" [>] Reading file: {}".format(action))
    actions_loaded.append(yaml.safe_load(open(action).read()))

####################################
##### Create Jupyter Notebooks #####
####################################

print("\n[+] Translating YAML files to notebooks..")
with open(notebooks_config_path, "r") as f:
    app_config = yaml.safe_load(f)

for action in actions_loaded:
    print("  [>>] Processing {} file..".format(action['name']))
    nb = nbf.v4.new_notebook()
    nb.metadata = {'kernelspec': {'language': 'python'}}
    nb['cells'] = []
    # Title
    nb['cells'].append(nbf.v4.new_markdown_cell("# {}".format(action['name'])))
    # Metadata
    nb['cells'].append(nbf.v4.new_markdown_cell("## Metadata"))
    techniques = []
    tactics = []
    metadata = action['metadata']
    execution = action['execution']
    if metadata['mitreAttack']:
        for obj in metadata['mitreAttack']:
            technique_name = obj['technique']
            technique_object = technique_name.split('.')
            technique_url = 'https://attack.mitre.org/techniques'
            if len(technique_object) > 1:
                technique_url = technique_url + "/" + technique_object[0] + "/" + technique_object[1]
            else:
                technique_url= technique_url + "/" + technique_name
            technique = "[{}]({})".format(technique_name,technique_url)
            if technique not in techniques:
                techniques.append(technique)
            if obj['tactics']:
                for tactic in obj['tactics']:
                    tactic_url = "https://attack.mitre.org/tactics/" + tactic
                    tactic = "[{}]({})".format(tactic,tactic_url)
                    if tactic not in tactics:
                        tactics.append(tactic)
    contributors = ','.join(metadata['contributors'])
    techniques = ','.join(techniques)
    tactics = ','.join(tactics)
    nb['cells'].append(nbf.v4.new_markdown_cell("""
|                   |    |
|:------------------|:---|
| platform          | {} |
| contributors      | {} |
| creation date     | {} |
| modification date | {} |
| Tactics           | {} |
| Techniques        | {} |""".format(platform_maps[execution['platform']],contributors,metadata['creationDate'],metadata['modificationDate'],tactics,techniques)
    ))
    # Description
    nb['cells'].append(nbf.v4.new_markdown_cell("""## Description
{}""".format(metadata['description'])))
    # Run Simulation
    nb['cells'].append(nbf.v4.new_markdown_cell("## Run Simulation"))
    # Authenticate
    nb['cells'].append(nbf.v4.new_markdown_cell("### Get OAuth Access Token"))
    nb['cells'].append(nbf.v4.new_code_cell("""from msal import PublicClientApplication
import requests
import time

function_app_url = "{}"

tenant_id = "{}"
public_client_app_id = "{}"
server_app_id_uri = "api://" + tenant_id + "/cloudkatana"
scope = server_app_id_uri + "/user_impersonation"

app = PublicClientApplication(
    public_client_app_id,
    authority="https://login.microsoftonline.com/" + tenant_id
)
result = app.acquire_token_interactive(scopes=[scope])
bearer_token = result['access_token']""".format(app_config['FUNCTION_APP_URL'],app_config['TENANT_ID'],app_config['PUBLIC_CLIENT_APP_ID'])))
    # Set Azure Function Orchestrator
    nb['cells'].append(nbf.v4.new_markdown_cell("### Set Azure Function Orchestrator"))
    nb['cells'].append(nbf.v4.new_code_cell("endpoint = function_app_url + \"/api/orchestrators/Orchestrator\""))
    # Create HTTP Body
    nb['cells'].append(nbf.v4.new_markdown_cell("### Prepare HTTP Body"))
    data_dict = dict()
    data_dict['RequestId'] = str(uuid.uuid4())
    data_dict['name'] = action['name']
    data_dict['metadata'] = metadata
    action['number'] = 1
    steps = [action]
    # Processing steps
    for step in steps:
        if 'parameters' in step['execution'].keys():
            stepParams = dict()
            for pk, pv in step['execution']['parameters'].items():
                if 'defaultValue' in pv.keys():
                    stepParams[pk] = step['execution']['parameters'][pk]['defaultValue']
                if 'required' in pv.keys():
                    if pv['required'] == true:
                        if 'type' in pv.keys():
                            if pv['type'] == 'array':
                                stepParams[pk] = ['ENTER-VALUE']
                            else:
                                stepParams[pk] = 'ENTER-VALUE'
            step['execution']['parameters'] = stepParams
    data_dict['steps'] = steps         
    data_json = json.dumps(data_dict)

    nb['cells'].append(nbf.v4.new_code_cell("data = [{}]".format(data_dict)))
    nb['cells'].append(nbf.v4.new_markdown_cell("### Send HTTP Request"))
    nb['cells'].append(nbf.v4.new_code_cell("""http_headers = {'Authorization': 'Bearer ' + bearer_token, 'Accept': 'application/json','Content-Type': 'application/json'}
results = requests.get(endpoint, json=data, headers=http_headers, stream=False).json()

time.sleep(30)"""))
    nb['cells'].append(nbf.v4.new_markdown_cell("### Explore Output"))
    nb['cells'].append(nbf.v4.new_code_cell("""query_status = requests.get(results['statusQueryGetUri'], headers=http_headers, stream=False).json()
query_results = query_status['output']
query_results"""))

    platform = platform_maps[execution['platform']].lower()
    # ***** Update Summary Tables *******
    for table in summary_table:
        if platform in table['platform'].lower():
            for attack in metadata['mitreAttack']:
                for tactic in attack['tactics']:
                    action['location'] = tactic_maps[tactic]
                    if action not in table['action']:
                        table['action'].append(action)
                    if tactic_maps[tactic] not in table['tactics']:
                        table['tactics'].append(tactic_maps[tactic])

    # ***** Create Notebooks *****
    for attack in metadata['mitreAttack']:
        for tactic in attack['tactics']:
            platform_folder_path = "{}/{}".format(simulations_directory,platform)
            tactic_folder_path = "{}/{}".format(platform_folder_path,tactic_maps[tactic])
            intro_file = '{}/intro.md'.format(tactic_folder_path)
            # creating directory for notebooks if they have not been created yet
            if not os.path.exists(tactic_folder_path):
                print(" [>] Creating notebook docs directory: {}".format(tactic_folder_path))
                # create directory
                os.makedirs(tactic_folder_path)
            if not os.path.exists(intro_file):
                print(" [>] Creating intro file: {}".format(intro_file))
                with open(intro_file, 'x') as f:
                    f.write('# {}'.format(tactic_maps[tactic]))

            #notebook_path = "{}/{}.ipynb".format(tactic_folder_path,action['title'])
            notebook_path = "{}/{}.md".format(tactic_folder_path,(action['name']).lower().replace(" ","_"))
            print(" [>] Creating notebook: {}".format(notebook_path))
            #nbf.write(nb, notebook_path)
            jupytext.write(nb, notebook_path, fmt='md')

##################################
##### Creating ATT&CK Layers #####
##################################
# Create ATT&CK Layer
print("\n[+] Creating ATT&CK navigator layers for each platform..")
# Reference: https://github.com/mitre-attack/car/blob/master/scripts/generate_attack_nav_layer.py#L30-L45
for summary in summary_table:
    if len(summary['action']) > 0:
        platform_folder_path = "{}/{}".format(simulations_directory,summary['platform'])
        techniques_mappings = dict()
        for action in summary['action']:
            metadataLayer = dict()
            metadataLayer['name'] = action['name']
            metadataLayer['value'] = action['id'] 
            for coverage in action['metadata']['mitreAttack']:
                technique = coverage['technique']
                if technique not in techniques_mappings:
                    techniques_mappings[technique] = []
                    techniques_mappings[technique].append(metadataLayer)
                elif technique in techniques_mappings:
                    if metadata not in techniques_mappings[technique]:
                        techniques_mappings[technique].append(metadataLayer)
        
        LAYER_VERSION = "4.3"
        ATTACK_VERSION = "11"
        NAVIGATOR_VERSION = "4.5.1"
        NAME = "Cloud Katana {} ATT&CK Coverage".format(summary['platform'])
        DESCRIPTION = "Techniques covered by Cloud Katana"
        DOMAIN = "mitre-enterprise"

        if summary['platform'] == 'Windows':
            PLATFORMS_FILTER = [
                'Windows'
            ]
        elif summary['platform'] == 'Azure':
            PLATFORMS_FILTER = [
                "Office 365",
                "AWS",
                "GCP",
                "Azure AD",
                "Azure",
                "SaaS"
            ]

        print("  [>>] Creating navigator layer for {} actions..".format(summary['platform']))
        katana_layer = {
            "description": DESCRIPTION,
            "name": NAME,
            "domain": DOMAIN,
            "versions": {
                "attack": ATTACK_VERSION,
                "navigator": NAVIGATOR_VERSION,
                "layer": LAYER_VERSION
            },
            "filters": {
                "platforms": PLATFORMS_FILTER
            },
            "techniques": [
                {
                    "score": 1,
                    "techniqueID" : k,
                    "metadata": v
                } for k,v in techniques_mappings.items()
            ],
            "gradient": {
                "colors": [
                    "#ffffff",
                    "#66fff3"
                ],
                "minValue": 0,
                "maxValue": 1
            },
            "legendItems": [
                {
                    "label": "Techniques researched",
                    "color": "#66fff3"
                }
            ]
        }
        open('{}/{}.json'.format(platform_folder_path,summary['platform'].lower()), 'w').write(json.dumps(katana_layer))

#################################
##### Create Summary Tables #####
#################################

print("\n[+] Creating action summary tables for each platform..")
summary_template = Template(open(summary_table_template).read())
for summary in summary_table:
    if len(summary['action']) > 0:
        print("  [>>] Creating summary table for {} actions..".format(summary['platform']))
        summary_for_render = copy.deepcopy(summary)
        markdown = summary_template.render(summary=summary_for_render)
        open('{}/{}/intro.md'.format(simulations_directory,summary['platform'].lower()), 'w').write(markdown)

###############################
##### Update TOC Template #####
###############################

print("\n[+] Creating TOC file..")
with open (toc_template) as json_file:
    toc_template_loaded = json.load(json_file)

# Iterate over Toc Template
for part in toc_template_loaded['parts']:
    if part['caption'] == 'Targeted Notebooks':
        for table in summary_table:
            table_platform = table['platform'].lower()
            if len(table['action']) > 0:
                action_platform = {
                    "file": "simulate/{}/intro".format(table_platform),
                    "sections": [
                        {
                            "file": "simulate/{}/{}/intro".format(table_platform,tactic),
                            "sections": [
                                {
                                    "file": "simulate/{}/{}/{}".format(table_platform,tactic,(action['name']).lower().replace(" ","_"))
                                } for action in table['action'] for maps in action['metadata']['mitreAttack'] for t in maps['tactics'] if tactic_maps[t] == tactic
                            ]
                        } for tactic in sorted(table['tactics'])
                    ]
                }
                part['chapters'].append(action_platform)

# ******* Update Jupyter Book TOC File *************
print("\n[+] Writing final TOC file for Jupyter book..")
with open(toc_file, 'w') as file:
    yaml.dump(toc_template_loaded, file, sort_keys=False)

####################################
##### Creating Azure Functions #####
####################################

##### Aggregating modules #####
modules = []
for action in actions_loaded:
    if action['execution']['platform'] == 'Azure':
        if 'module' in action['execution'].keys():
            mod_dict = dict()
            mod_dict['name'] = action['execution']['module']['name']
            mod_dict['version'] = action['execution']['module']['version']
            if mod_dict not in modules:
                modules.append(mod_dict)
if len(modules) > 0:
    print("\n[+] Aggregating PowerShell modules..")
    print(modules)

##### Aggregating Permissions #####
permissions = dict()
for action in actions_loaded:
    if 'authorization' in action.keys():
        for ap in action['authorization']:
            permission_type = ap['permissionsType']
            roles = ap['permissions']
            if permission_type not in permissions:
                permissions[permission_type] = []
            for r in roles:
                if r not in permissions[permission_type]:
                    permissions[permission_type].append(r)
print("\n[+] Creating permissions file..")
open('{}/permissions.json'.format(metadata_directory), 'w').write(json.dumps(permissions, indent = 4))

# Creating PowerShell Requirements file
print("\n[+] Creating PowerShell Requirements file..")
pwsh_req_template_loaded = Template(open(pwsh_req_template).read())
if len(modules) > 0:
    file_path = '{}/requirements.psd1'.format(app_directory)
    mods_for_render = copy.deepcopy(modules)
    mods_req = pwsh_req_template_loaded.render(mods=mods_for_render)
    open(file_path, 'w').write(mods_req)