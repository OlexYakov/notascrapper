import configparser
from pyclbr import Function
from re import sub
from typing import Dict, List, Tuple
from bs4 import BeautifulSoup
import re
import json
import requests
from requests import Response
from requests.sessions import Session
import logging
from time import sleep
config = None
configs_file_name = 'configs.ini'
infor_base_url = "https://inforestudante.uc.pt"
infor_login_url = infor_base_url+"/nonio/security/login.do"
infor_insc_turmas_url = infor_base_url + "/nonio/inscturmas/init.do"
infor_subjects_url = infor_base_url + \
    "/nonio/inscturmas/listaInscricoes.do?args=5189681149284684"
infor_pautas_url = infor_base_url+"/nonio/pautas/pesquisaPautas.do"
infor_init_url = infor_base_url+"/security/init.do"


class Subject():
    '''
    Helper class for holding data for each subject
    '''
    number: str
    name: str
    semester: str
    href: str
    url: str

    @staticmethod
    def fromBSTableList(elems: List):
        d = Subject()

        d.number = NoneIfException(lambda e: e.text, elems[0])
        d.name = NoneIfException(lambda e: e.span.text, elems[1])
        if d.name is None:
            d.name = NoneIfException(lambda e: e.text, elems[1])

        d.name = d.name.split("*")[0].strip()
        d.semester = NoneIfException(lambda e: e.text, elems[2])
        d.href = NoneIfException(lambda e: e.a["href"], elems[6])

        return d

    def __repr__(self) -> str:
        return "{} {} {} {}".format(
            self.semester, self.number, self.name, self.url
        )


class Form():
    id: str
    action_url: str
    inputs: Dict = {}

    @staticmethod
    def fromBSForm(form: BeautifulSoup):
        irrelevant_inputs = ['visibilidade',
                             'org.apache.struts.taglib.html.CANCEL']
        f = Form()
        f.id = form["id"]
        f.action_url = gen_link(infor_base_url, form["action"])
        inputs = form.find_all("input")
        for i in inputs:
            if i['name'] in irrelevant_inputs:
                continue
            if i['name'] not in f.inputs:
                f.inputs[i['name']] = [i.attrs]
            else:
                f.inputs[i['name']].append(i.attrs)

        return f

    def __repr__(self) -> str:
        return f"{self.id}\t{self.action_url}\t{self.inputs}"


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
    global configs_file_name
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
                logging.info(
                    f'Config file doesnt have the {val}. Please fill it in')
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
                logging.info(err.message)
                return None
    except FileNotFoundError:
        logging.info(
            f'Config file not found. Created new file "{configs_file_name}. Open it and change your username and password."')
        regen_config_file()
        return None


def login(session: Session) -> Tuple[bool, Response]:
    # GET infor page
    r = session.get(infor_login_url)
    logging.info(f"GET {infor_login_url}, status: {r.status_code}")
    if r.status_code != 200:
        return (False, r)

    page = BeautifulSoup(r.text, 'html.parser')
    cookie = r.headers["Set-Cookie"].split()[0]
    # TODO the cookie is set in the request itself
    session.headers.update({"Cookie": cookie})

    login_form = page.find(id="loginFormBean")
    action = login_form["action"]

    login_url = infor_base_url+action

    # POST login attempt
    form_data = {
        "username": config.defaults()['username'],
        "password": config.defaults()['password']}
    r = session.post(login_url, data=form_data)

    logging.info(f"POST Login request status: {r.status_code}")
    if r.status_code != 200:
        return (False, r)

    # Check if correctly authenticated
    page = BeautifulSoup(r.text, 'html.parser')
    errors_div = page.find(id="div_erros_preenchimento_formulario")
    if errors_div is not None:
        error_text = errors_div.div.ul.li.text
        logging.info(error_text)
        return (False, r)
    return (True, r)


def navigate_subjects_page(session: Session) -> Tuple[bool, Response]:
    # Get list of classes
    r = session.get(infor_insc_turmas_url)
    if r.status_code != 200:
        logging.info(r.status_code)
        return False, None
    page = BeautifulSoup(r.text, 'html.parser')
    # TODO avisar caso LEI não se a primeira
    next_link_part = page.find(id="link_0").a["href"]
    url = gen_link(infor_insc_turmas_url, next_link_part)
    r = session.post(url)
    if r.status_code != 200:
        logging.info(r.status_code)
        return False, None

    return True, r


def extract_subjects(res: Response) -> List[Subject]:
    '''
    Extracts the subjects from the http response containing the 'listaInscricoesFormBean'.
    Every subject has a url property, in wich the classes (Theory and Practical) can be found.
    '''
    page = BeautifulSoup(res.text, 'html.parser')
    subjects_form = page.find(id="listaInscricoesFormBean")
    if subjects_form is None:
        raise Exception('Cant find the subjects list')
    subjects_table_rows = subjects_form.find(
        class_="displaytable").tbody.find_all("tr")

    # Filter

    subjects = [Subject.fromBSTableList([i for i in row if i != "\n"])
                for row in subjects_table_rows]
    for sub in subjects:
        sub.url = gen_link(infor_subjects_url,
                           sub.href) if sub.href is not None else None
    return subjects


def NoneIfException(f: Function, *args):
    try:
        return f(*args)
    except Exception as e:
        # logging.info(e)
        return None


def gen_classes_configs(subjects: List[Subject], session: Session):
    relevant_subs = [
        "Teórico-Prática",
        "Teórico-Práticas",
        "Práticas-Laboratoriais"
    ]

    turmas = {}

    for d in [d for d in subjects if d.url != None]:

        turmas[d.name] = {}

        r = session.get(d.url)
        if r.status_code != 200:
            logging.info(f"GET {d.url} status {r.status_code}")
            exit()

        page = BeautifulSoup(r.text, 'html.parser')
        form = page.find(id="listaInscricoesFormBean")
        if form is None:
            form = page.find(id="inscreverFormBean")
        if form is None:
            logging.info("Something went wrong. Cant find form")
            continue
        # form = Form.fromBSForm(form)
        form_url = gen_link(infor_base_url, form['action'])
        form_submit_button = form.find('input', type="submit")
        if form_submit_button is None:
            logging.info("submit button not found")
        else:
            logging.info(form_submit_button)
        zones = form.find_all(class_="zone")

        for zone in zones:
            zoneTitle = zone.find(class_="subtitle")
            if zoneTitle is not None:
                zoneTitle = zoneTitle.text.strip()
                logging.info(f"Zone title: {zoneTitle}")
            else:
                logging.info("No zone title")
            if zoneTitle not in relevant_subs:
                continue

            turmas[d.name][zoneTitle] = {
                "choise": "ESCOLHE UMA OPCAO", "options": []}

            zoneContent = zone.find(class_="zonecontent")
            zoneDispTable = zone.find(class_="displaytable")
            if zoneDispTable is None:
                text = re.sub(r'\s+', ' ', zoneContent.text)
                logging.info(text)
                continue

            zoneRows = zoneDispTable.find_all("tr")
            for row in zoneRows:
                zoneCols = row.find_all("td")
                # logging.info("TP1" in map(lambda c: c.text, zoneCols))
                if (len(zoneCols) > 0):
                    turmas[d.name][zoneTitle]["options"].append(
                        re.sub(r'\s+', ' ', zoneCols[0].text))
                for col in zoneCols:
                    text = re.sub(r'\s+', ' ', col.text)
                    logging.info(text, end="\t")
                logging.info("")

    with open("turmas.json", "w") as f:
        json.dump(turmas, f)


def do_register(subjects: List[Subject], session: Session):
    def turma_tag(bs: BeautifulSoup) -> bool:
        return bs.name == 'input' and not bs['name'] == 'visibilidade' and not bs['name'] == "org.apache.struts.taglib.html.CANCE"

    relevant_subs = [
        "Teórico-Prática",
        "Teórico-Práticas",
        "Práticas-Laboratoriais"
    ]
    try:
        turmas = json.load(open("turmas.json"))
    except FileNotFoundError:
        logging.info(
            "turmas.json file not found. Run gen_classes_config first")
        # TODO do you want to run it now?
        return
    except:
        return

    for d in [d for d in subjects if d.url != None]:
        fields = {}
        r = session.get(d.url)
        if r.status_code != 200:
            logging.info(f"GET {d.url} status {r.status_code}")
            exit()

        page = BeautifulSoup(r.text, 'html.parser')
        form = page.find(id="listaInscricoesFormBean")
        if form is None:
            form = page.find(id="inscreverFormBean")
        if form is None:
            logging.info("Something went wrong. Cant find form")
            continue
        # form = Form.fromBSForm(form)
        form_url = infor_base_url + form['action']
        # form_submit_button = form.find('input', type="submit")
        # if form_submit_button is None:
        #     logging.info("submit button not found")
        # else:
        #     logging.info(form_submit_button)
        zones = form.find_all(class_="zone")

        for zone in zones:
            zoneTitle = zone.find(class_="subtitle")
            if zoneTitle is None:
                continue
            zoneTitle = zoneTitle.text.strip()
            if zoneTitle not in relevant_subs:
                continue
            logging.info(f"Zone title: {d.name} - {zoneTitle}")

            zoneContent = zone.find(class_="zonecontent")
            zoneDispTable = zone.find(class_="displaytable")
            if zoneDispTable is None:
                text = re.sub(r'\s+', ' ', zoneContent.text)
                logging.info(text)
                continue

            zoneRows = zoneDispTable.find_all("tr")
            choise = turmas[d.name][zoneTitle]["choise"]
            options = list(filter(lambda c: choise in c.text, zoneRows))
            if len(options) == 0:
                logging.info(f"No option {choise} for {zoneTitle} in {d.name}")
                continue

            option = options[0]

            inp = option.find(turma_tag)
            if inp is None:
                logging.info(
                    f"Something went wrong: {option.find_all('td')[-1].text.strip()}")
                continue

            fields[inp['name']] = inp['value']

        if len(fields) != 0:
            logging.info(f"TRY: POST {form_url} with fields: {fields}")
            # r = session.post(form_url, data=fields )

            # if r.status_code != 200:
            #     logging.info(
            #         f"Register to {d.name} with fields {form} failed with status {r.status_code}")
            # TODO check if url redirected to https://inforestudante.uc.pt/nonio/inscturmas/listaInscricoes.do


def class_sniper(subject: Subject, turma: str, session: Session, time=10):
    def turma_tag(bs: BeautifulSoup) -> bool:
        return bs.name == 'input' and not bs['name'] == 'visibilidade' and not bs['name'] == "org.apache.struts.taglib.html.CANCE"

    relevant_subs = [
        "Teórico-Prática",
        "Teórico-Práticas",
        "Práticas-Laboratoriais"
    ]
    fields = {}
    logging.info(
        f"Begining to snipe class {turma} for {subject.name} with {time} second intervals")
    r = session.get(subject.url)
    if r.status_code != 200:
        logging.error(
            f"Recieved status code {r.status_code} while sniping. Reason:{r.reason}")
        return

    page = BeautifulSoup(r.text, 'html.parser')
    form = page.find(id="listaInscricoesFormBean")
    if form is None:
        form = page.find(id="inscreverFormBean")
    if form is None:
        logging.info("Something went wrong. Cant find form")
        return
    # form = Form.fromBSForm(form)
    form_url = infor_base_url + form['action']
    # form_submit_button = form.find('input', type="submit")
    # if form_submit_button is None:
    #     logging.info("submit button not found")
    # else:
    #     logging.info(form_submit_button)
    zones = form.find_all(class_="zone")

    for zone in zones:
        zoneTitle = zone.find(class_="subtitle")
        if zoneTitle is None:
            continue
        zoneTitle = zoneTitle.text.strip()
        if zoneTitle not in relevant_subs:
            continue
        logging.info(f"Zone title: {subject.name} - {zoneTitle}")

        zoneContent = zone.find(class_="zonecontent")
        zoneDispTable = zone.find(class_="displaytable")
        if zoneDispTable is None:
            text = re.sub(r'\s+', ' ', zoneContent.text)
            logging.info(text)
            continue

        zoneRows = zoneDispTable.find_all("tr")

        options = list(filter(lambda c: turma in c.text, zoneRows))
        if len(options) == 0:
            logging.info(
                f"No option {turma} for {zoneTitle} in {subject.name}")
            continue

        option = options[0]

        inp = option.find(turma_tag)
        if inp is None:
            logging.info(
                f"Something went wrong: {option.find_all('td')[-1].text.strip()}")
            # Extract input value from the horarios input
            value = option.find('input')['value']
            fields["inscrever"] = value
        else:
            vagas = option.find_all('td')[-3].text
            logging.info(f"You're in luck, a turma ainda tem {vagas}")
            fields[inp['name']] = inp['value']
        break
    logging.info(f"Payload ready, fields to post: {fields}")
    while True:
        r = session.post(form_url, data=fields)
        logging.info(f"Posted, res status code: {r.status_code}, url: {r.url}")
        if r.status_code != 200:
            return

        if r.url == "https://inforestudante.uc.pt/nonio/inscturmas/listaInscricoes.do":
            logging.info("Gotcha!")
            return
        elif r.url == "https://inforestudante.uc.pt/nonio/inscturmas/inscrever.do?method=submeter":
            logging.info("Not yet.. trying again")
            r = session.get(
                "https://inforestudante.uc.pt/nonio/inscturmas/listaInscricoes.do")
            r = session.get(subject.url)
        with open("test.html", "w") as f:
            f.write(r.text)
        # TODO log answer
        sleep(time)


if __name__ == "__main__":
    config = load_configs()
    if config is None:
        exit()
    logging.basicConfig(
        format="%(asctime)s %(levelname)-8s %(message)s",
        level=logging.INFO,
        datefmt="%H:%M:%S")
    session = requests.Session()

    success, res = login(session)
    if not success:
        logging.info("Login attempt failed")
        exit()
    logging.info("Login successfull")

    success, res = navigate_subjects_page(session)
    if not success:
        logging.info("Could not reach the LEI subjects page")
        exit()
    logging.info("Inside classes page")

    subjects = extract_subjects(res)

    # gen_classes_configs(subjects,session)
    # do_register(subjects, session)
    class_sniper(next(s for s in subjects if s.name ==
                      "Interação Humano-Computador"),
                 "PL1",
                 session)
