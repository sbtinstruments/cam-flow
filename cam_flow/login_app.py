import aiohttp
import asyncio
import json
import pathlib
import os
import base64
import logging
import progbar
import sys
import getpass

from aiohttp.client_exceptions import ClientConnectorError

logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.INFO)
_LOGGER = logging.getLogger(__name__)
_LOGGER.addHandler(logging.StreamHandler(sys.stdout))



HOST = 'http://172.17.197.78:3000/'
STACK = '1A211'
_STACK = '1B111'

def _is_visual(x):
    if x['name'] == 'visual':
        return True
    return False

def _is_my_stack(x):
    if _STACK in x['stack_full_id']:
        return True
    return False

def _get_pos(x):
    return x['stack_position']

def getCredentials():
    user = input('Username: ')
    secret = getpass.getpass()
    return {'user': user, 'password': secret}

async def logMeIn(session, data):
    """Logs you in the server"""
    async with session.post(HOST+'auth',data=data) as resp:
        return await resp.json()

async def getVisualQcTempalte(session):
    async with session.get(HOST+'templates') as resp:
        return await resp.json()

async def getStackID(session):
    async with session.get(HOST+'flowcells//?stacks=full_id') as resp:
        return await resp.json()

async def getFlowcellIdFromDb(session, stack_id:str):
    async with session.get(HOST+f'flowcells/?stacks={stack_id}') as resp:
        return await resp.json()

async def uploadReport(session, data):
    async with session.post(HOST+'reports',json=data) as resp:
        return resp

def get_report_data(json_response):
    visual_templates = filter(_is_visual, json_response)
    visual_templates = (list(visual_templates))
    
    max_visual_templ = max(visual_templates,key=lambda x: x['ver'])
    template_ver = max_visual_templ['ver']
    qc_questions = list(max_visual_templ['questions']['properties'].keys())
    # TODO: template DSL -> template_picture_key to picture_file_name mapping: picture1: *_top.jpg
    return {"report":{
        "report_type":"flowcell",
        "template_name":"visual",
        "template_ver":template_ver,
        "last_edited_by":None,
        "answers":
            {i:None for i in qc_questions},
        "status":"FAILED"},
    "subId":None}

def get_file2json_config():
    """Read in json config"""
    file_path = pathlib.Path(__file__).parent / "config.json"
    with open(file_path) as f:
        config = json.load(f)
    return config

def get_flowcell_list(stack_string):
    stack_dir_path = pathlib.Path.cwd() / stack_string
    sub_dirs = os.listdir(stack_dir_path)
    return [x for x in sub_dirs if stack_string in x]
     
def read_images(path,conf:dict):
    out = {}
    file_ls = os.listdir(path)
    for (k,v) in conf.items():
        file = [x for x in file_ls if v in x]
        if len(file) != 1:
            _LOGGER.warning("Could not match %s / %s",path,v)
            continue
        file = file[0]
        with open(path / file, "rb") as image_file:
            out[k] = base64.b64encode(image_file.read()).decode("utf-8")
    
    return out


async def main():
    _LOGGER.debug("Started")
    auth = None
    # TODO: remove after dev
    jar = aiohttp.CookieJar(unsafe=True)
    async with aiohttp.ClientSession(cookie_jar=jar) as session:
        log_in = getCredentials()
        response = await logMeIn(session,log_in)
        try:
            user_id = response["id"]
        except KeyError as exc:
            raise KeyError("Could not retrieve authorization response.") from exc

        _LOGGER.info("Login successful.")

        qc_templates = await getVisualQcTempalte(session)
        json_data = get_report_data(qc_templates)       
        json_data["report"]["created_by"] = str(user_id)
        json_data["report"]["last_edited_by"] = str(user_id)

        conf = get_file2json_config()

        local_dir_list = get_flowcell_list(STACK)
        db_stack_id_list = await getStackID(session)
        db_stack_id = list(filter(_is_my_stack,db_stack_id_list))
        if len(db_stack_id) == 0:
            print("This stack does not exist in the QC system. First create it via the online interface.")
            return

        out_info = {"stack":db_stack_id[0]["stack_full_id"]}
        db_stack_id = db_stack_id[0]["id"]
        flow_cell_list = await getFlowcellIdFromDb(session,db_stack_id)

        
        for sub_dir in progbar.progressBar(local_dir_list, prefix='Progress:',suffix = 'Complete', length = 50):
            if sub_dir[-3:-1] not in map(_get_pos, flow_cell_list):
                out_info[sub_dir[-3:-1]] = "Not found."
                _LOGGER.info("%s not found.",sub_dir[-3:-1])
                continue
            # tmp copy of report
            out_info[sub_dir[-3:-1]] = {}
            tmp_rep = json_data
            p = pathlib.Path.cwd()/ STACK / sub_dir
            tmp_img = read_images(p, conf)
            for (k,v) in tmp_img.items():
                out_info[sub_dir[-3:-1]][k] = "OK" if len(v) > 10 else "FAILED"
                tmp_rep["report"]["answers"][k] = "data:image/jpeg;base64," + v

            fcell = next((item for item in flow_cell_list if item["stack_position"] == sub_dir[-3:-1]), None)
            tmp_rep["subId"] = fcell["id"]
            with open("output.json","w") as f:
                json.dump(tmp_rep,f)
            res = await uploadReport(session, tmp_rep)
            _LOGGER.debug("%s ",res.status)
            out_info[sub_dir[-3:-1]]["upload"] = "OK" if res.status == 200 else "FAILED"
        

        _LOGGER.info(json.dumps(out_info,indent=2))
        print("\n[ DONE ]\n")
        
        


loop = asyncio.get_event_loop()
loop.run_until_complete(main())