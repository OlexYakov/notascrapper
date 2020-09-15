import configparser
from typing import Tuple
from bs4 import BeautifulSoup

import urllib3
from urllib3.poolmanager import PoolManager
from urllib3.response import HTTPResponse

config = None
infor_base_url = "https://inforestudante.uc.pt"
infor_login_url = infor_base_url+"/nonio/security/login.do"
infor_turmas_url = infor_base_url + \
    "/nonio/inscturmas/listaInscricoes.do?args=5189681149284684"
infor_pautas_url = infor_base_url+"/nonio/pautas/pesquisaPautas.do"
headers = {}


def gen_link(path: str, dest: str) -> str:
    path = path.split("/")[:-1]
    dest = dest.split("/")

    while len(dest) != 0:
        elem = dest.pop(0)
        if elem == "..":
            path.pop(-1)
        else:
            path.append(elem)

    return path[0]+"/"+"/".join(path[1:])


def load_configs() -> configparser.ConfigParser:
    '''Load configurations from the default configs.ini file'''

    configs_file_name = 'configs.ini'
    config = configparser.ConfigParser()
    defaults = {
        'DEFAULT': {
            'username': 'EMAIL_UC',
            'password': 'PASS_UC'
        }
    }

    def regen_config_file():
        f = open(configs_file_name, 'w')
        # Populate with default data
        config.read_dict(defaults)
        config.write(f)
        f.close()
        return None

    def valid_user_info() -> bool:
        errors = False
        for val in ('username', 'password'):
            if val not in config.defaults():
                print(f'Config file doesnt have the {val}. Please fill it in')
                config.defaults()[val] = defaults['DEFAULT'][val]
                errors = True
        return not errors

    try:
        with open(configs_file_name, 'r+') as f:
            try:
                config.read_file(f)
                if not valid_user_info():
                    f.seek(0)
                    config.write(f)
                    return None
                return config
            except configparser.ParsingError as err:
                print(err.message)
                return None
    except FileNotFoundError:
        print(
            f'Config file not found. Created new file "{configs_file_name}. Open it and change your username and password."')
        regen_config_file()
        return None


def login(http: PoolManager) -> Tuple[bool, HTTPResponse]:
    # GET infor page
    r = http.request('GET', infor_login_url)
    print(f"GET {infor_login_url}, status: {r.status}")
    if r.status != 200:
        return (False, r)

    page = BeautifulSoup(r.data, 'html.parser')
    cookie = r.headers["Set-Cookie"].split()[0]
    global headers
    headers["Cookie"] = cookie

    login_form = page.find(id="loginFormBean")
    action = login_form["action"]

    login_url = infor_base_url+action

    # POST login attempt
    form_data = {
        "username": config.defaults()['username'],
        "password": config.defaults()['password']}
    r = http.request('POST', login_url, fields=form_data, retries=5)

    print(f"POST Login request status: {r.status}")
    if r.status != 200:
        return (False, r)

    # Check if correctly authenticated
    page = BeautifulSoup(r.data, 'html.parser')
    errors_div = page.find(id="div_erros_preenchimento_formulario")
    if errors_div is not None:
        error_text = errors_div.div.ul.li.text
        print(error_text)
        return (False, r)
    return (True, r)


if __name__ == "__main__":
    config = load_configs()
    if config is None:
        exit()

    http = urllib3.PoolManager()
    success, res = login(http)
    if not success:
        print("Login attempt failed")
        exit()
    print("Login successfull")

    # Get list of classes
    r = http.request(
        'GET', "https://inforestudante.uc.pt/nonio/inscturmas/init.do", headers=headers)
    if r.status != 200:
        print(r.status)
        exit()  # TODO
    page = BeautifulSoup(r.data, 'html.parser')
    # TODO avisar caso LEI não se a primeira
    next_link_part = page.find(id="link_0").a["href"]
    url = gen_link(r.geturl(), next_link_part)
    print(url)
    r = http.request('GET', url, headers=headers)
    # DEBUG
    with open("temp.html", 'w') as f:
        f.write(r.data.decode())
    if r.status != 200:
        print(r.status)
        exit()  # TODO
    page = BeautifulSoup(r.data, 'html.parser')

    turmas_list_form = page.find(id="listaInscricoesFormBean")

    turmas_table_rows = turmas_list_form.find(
        class_="displaytable").tbody.find_all("tr")

    for row in turmas_table_rows:
        print(row.contents[3].text)
