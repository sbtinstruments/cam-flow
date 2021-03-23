import aiohttp
import time
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.popup import Popup
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.progressbar import ProgressBar
from cam_flow import my_text_progbar


import json
import pathlib
import os
import base64
import logging
import sys
import asyncio

logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.INFO)
_LOGGER = logging.getLogger(__name__)
_LOGGER.addHandler(logging.StreamHandler(sys.stdout))

_STACK = '1B111'

HOST = 'https://qc-api.sbtinstruments.com/'
spacer = (50,50)

labelProps = {
    "max_lines":1,
    # "text_size":(10, 20),
    "halign":"left",
    "valign":"bottom",
    "size_hint":(0.8,0.2),
}

textInputProps = {
    "halign":"left",
    "multiline":False,
    "size_hint":(1, 0.3),
    "background_color":(0.1, 0.1, 0.1, 0.9),
    "selection_color":(0.18, 0.65, 0.83, 0.3),
    "cursor_color":(1,1,1,1),
    "foreground_color":(1,1,1,1),
}

buttonProps = {
    "halign":"center",
    "size_hint":(1, 0.25),
}

def _is_visual(x):
    if x['name'] == 'visual':
        return True
    return False


def _get_pos(x):
    return x['stack_position']

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
        l = await resp.text()
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



class LoginPopup(Popup):
    """Log in interface with upload"""
    def __init__(self):
        super(LoginPopup, self).__init__()
        self.title = 'Upload visual QC images'
        self.size = (250, 400)
        self.size_hint = (None,None)
        UserNameLabel = Label(
            text="e-mail", **labelProps
        )
        UserNameLabel.bind(size=UserNameLabel.setter('text_size'))
        user_name = ''
        self.UserName = TextInput(
            text=user_name,
            **textInputProps
        )
        UserPwLabel = Label(
            text="password", **labelProps
        )
        UserPwLabel.bind(size=UserPwLabel.setter('text_size'))
        password=''
        self.UserPw = TextInput(
            text=password,
            password=True,
            **textInputProps
        )

        self.stack_name = None
        self.logInButton = Button(text="Log in", on_press=self._logIn, disabled=False, **buttonProps)
        

        row = BoxLayout(
            orientation="vertical",
            padding=(20,20),
        )
        row.add_widget(Label(size=spacer, size_hint=(None,None)))
        row.add_widget(UserNameLabel)
        row.add_widget(self.UserName)
        row.add_widget(UserPwLabel)
        row.add_widget(self.UserPw)
        row.add_widget(Label(size=spacer, size_hint=(None,None)))
        row.add_widget(self.logInButton)
        row.add_widget(Label(size=spacer, size_hint=(None,None)))

        col0 = BoxLayout(
            orientation="horizontal"
        )
        col0.add_widget(Label(size=(1,50), size_hint=(None,None)))
        col0.add_widget(row)
        col0.add_widget(Label(size=(1,50), size_hint=(None,None)))

        self.content = col0

    def set_stack_name(self,name):
        self.stack_name = name
        return

    def on_open(self):
        self.UserName.focus = True

    
    def _is_my_stack(self, x):
        if self.stack_name in x['stack_full_id']:
            return True
        return False

    def _logIn(self, args):
        """Get authetication from server."""
        # run log in in coro
        self.logInButton.disabled = True
        task = asyncio.create_task(self.async_login())
        # Task is leaking here.
        self.logInButton.disabled = False
        

    async def async_login(self):
        _LOGGER.debug("Started")
        auth = None
        # NOTE: unsafe jar dev ONLY
        # jar = aiohttp.CookieJar(unsafe=True)
        # async with aiohttp.ClientSession(cookie_jar=jar) as session:
        async with aiohttp.ClientSession() as session:
            response = await logMeIn(session,{"user_name": self.UserName.text,"password": self.UserPw.text})
            try:
                user_id = response["id"]
            except KeyError as exc:
                raise KeyError("Could not retrieve authorization response.") from exc
            print(user_id)
            qc_templates = await getVisualQcTempalte(session)
            json_data = get_report_data(qc_templates)       
            json_data["report"]["created_by"] = str(user_id)
            json_data["report"]["last_edited_by"] = str(user_id)
            conf = get_file2json_config()
            local_dir_list = get_flowcell_list(self.stack_name)
            db_stack_id_list = await getStackID(session)
            db_stack_id = list(filter(self._is_my_stack,db_stack_id_list))
            if len(db_stack_id) == 0:
                print("This stack does not exist in the QC system. First create it via the online interface.")
                return

            out_info = {"stack":db_stack_id[0]["stack_full_id"]}
            db_stack_id = db_stack_id[0]["id"]
            flow_cell_list = await getFlowcellIdFromDb(session,db_stack_id)
            
            for sub_dir in my_text_progbar.progressBar(local_dir_list, prefix='Progress:',suffix = 'Complete', length = 50):
                if sub_dir[-3:-1] not in map(_get_pos, flow_cell_list):
                    out_info[sub_dir[-3:-1]] = "Not found."
                    _LOGGER.info("%s not found.",sub_dir[-3:-1])
                    continue
                # tmp copy of report
                out_info[sub_dir[-3:-1]] = {}
                tmp_rep = json_data
                p = pathlib.Path.cwd()/ self.stack_name / sub_dir
                tmp_img = read_images(p, conf)
                for (k,v) in tmp_img.items():
                    out_info[sub_dir[-3:-1]][k] = "OK" if len(v) > 10 else "FAILED"
                    tmp_rep["report"]["answers"][k] = "data:image/jpeg;base64," + v

                fcell = next((item for item in flow_cell_list if item["stack_position"] == sub_dir[-3:-1]), None)
                tmp_rep["subId"] = fcell["id"]
                with open("output.json","w") as f:
                    json.dump(tmp_rep,f)
                res = await uploadReport(session, tmp_rep)
                print(res.status)
                out_info[sub_dir[-3:-1]]["upload"] = "OK" if res.status == 200 else "FAILED"
            

            print(json.dumps(out_info,indent=2))
            print("\n[ DONE ]\n")
