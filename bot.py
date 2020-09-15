import configparser
from pyclbr import Function
from typing import List, Tuple
from bs4 import BeautifulSoup
import re

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


def NoneIfException(f: Function, *args):
    try:
        return f(*args)
    except Exception as e:
        # print(e)
        return None


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
    if r.status != 200:
        print(r.status)
        exit()  # TODO
    page = BeautifulSoup(r.data, 'html.parser')

    turmas_list_form = page.find(id="listaInscricoesFormBean")

    turmas_table_rows = turmas_list_form.find(
        class_="displaytable").tbody.find_all("tr")

    # Filter
    class Disciplina():
        numero: str
        nome: str
        semeste: str
        href: str
        url: str

        @staticmethod
        def fromBSTableList(elems: List):
            d = Disciplina()

            d.numero = NoneIfException(lambda e: e.text, elems[0])
            d.nome = NoneIfException(lambda e: e.span.text, elems[1])
            if d.nome is None:
                d.nome = NoneIfException(lambda e: e.text, elems[1])
            d.semeste = NoneIfException(lambda e: e.text, elems[2])
            d.href = NoneIfException(lambda e: e.a["href"], elems[6])

            return d

        def __repr__(self) -> str:
            return "{} {} {} {}".format(
                self.semeste, self.numero, self.nome, self.url
            )
    disciplinas = [Disciplina.fromBSTableList([i for i in row if i != "\n"])
                   for row in turmas_table_rows]

    for d in disciplinas:
        d.url = gen_link(infor_turmas_url,
                         d.href) if d.href is not None else None

    for d in [d for d in disciplinas if d.url != None]:
        r = http.request('GET', d.url, headers=headers)
        if r.status != 200:
            print(f"GET {d.url} status {r.status}")
            exit()
        # print(f"Getting turmas for {d.nome}")

        page = BeautifulSoup(r.data, 'html.parser')
        form = page.find(id="listaInscricoesFormBean")
        if form is None:
            form = page.find(id="inscreverFormBean")
        if form is None:
            print("Something went wrong. Cant find form")
            continue

        formActionUrl = gen_link(infor_base_url, form['action'])
        print(f"Form submit url: {formActionUrl}")
        formSubmitButton = form.find('input', type="submit")
        if formSubmitButton is None:
            print("submit button not found")
        else:
            print(formSubmitButton)
        zones = form.find_all(class_="zone")

        for zone in zones:
            zoneTitle = zone.find(class_="subtitle")
            if zoneTitle is not None:
                zoneTitle = zoneTitle.text.strip()
                print(f"Zone title: {zoneTitle}")
            else:
                print("No zone title")
            zoneContent = zone.find(class_="zonecontent")
            zoneDispTable = zone.find(class_="displaytable")
            if zoneDispTable is None:
                text = re.sub(r'\s+', ' ', zoneContent.text)
                print(text)
                continue

            zoneRows = zoneDispTable.find_all("tr")
            for row in zoneRows:
                zoneCols = row.find_all("td")
                for col in zoneCols:
                    text = re.sub(r'\s+', ' ', col.text)
                    print(text, end="\t")
                print("")
