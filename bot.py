#!/usr/bin/python3
import configparser
import datetime
from logging import log
from pyclbr import Function
from re import fullmatch, sub
import time
from typing import Deque, Dict, List, Tuple
from bs4 import BeautifulSoup
import re
import json
import requests
from requests import Response
from requests.sessions import Session
from dataclasses import dataclass
import logging
from time import sleep

config = None
configs_file_name = 'configs.ini'
turmas_file_name = "turmas.json"
infor_base_url = "https://inforestudante.uc.pt"
infor_login_url = infor_base_url + "/nonio/security/login.do"
infor_insc_turmas_url = infor_base_url + "/nonio/inscturmas/init.do"
infor_insc_turmas_base = infor_base_url + "/nonio/inscturmas/"
infor_subjects_url = infor_base_url + \
    "/nonio/inscturmas/listaInscricoes.do?args=5189681149284684"
infor_pautas_url = infor_base_url + "/nonio/pautas/pesquisaPautas.do"
infor_init_url = infor_base_url + "/security/init.do"
relevant_zone_titles = [
    "Teórico-Prática",
    "Teórico-Práticas",
    "Práticas-Laboratoriais",
    "Práticas e Laboratórios"
]


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


@dataclass
class Payload():
    subject: Subject
    form_url: str
    payload: Dict
    turma: str


def NoneIfException(f: Function, *args):
    '''
    Wrapper method. Returns None if an exception occurs.
    '''
    try:
        return f(*args)
    except Exception as e:
        # logging.info(e)
        return None


def is_turma_tag(tag: BeautifulSoup) -> bool:
    return tag.name == 'input' and \
        not tag['name'] == 'visibilidade' and \
        not tag['name'] == "org.apache.struts.taglib.html.CANCE"


def gen_link(path: str, dest: str) -> str:
    logging.debug(f"Concatinating {path} with {dest}")
    path = path.split("/")[:-1]
    dest = dest.split("/")

    while dest:
        elem = dest.pop(0)
        if elem == "..":
            path.pop(-1)
        else:
            path.append(elem)
    full_path = path[0] + "/" + "/".join(path[1:])
    logging.debug(f"Result: {full_path}")
    return full_path


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
    if r.status_code != 200:
        return (False, r)

    page = BeautifulSoup(r.text, 'html.parser')
    cookie = r.headers["Set-Cookie"].split()[0]
    # TODO the cookie is set in the request itself
    session.headers.update({"Cookie": cookie})

    login_form = page.find(id="loginFormBean")
    action = login_form["action"]

    login_url = infor_base_url + action

    # POST login attempt
    form_data = {
        "username": config.defaults()['username'],
        "password": config.defaults()['password']}
    r = session.post(login_url, data=form_data)

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


def navigate_subjects_page(session: Session, relogin: bool = True) -> Tuple[bool, Response]:
    # Get list of classes
    r = session.get(infor_insc_turmas_url)
    if r.status_code != 200:
        logging.info(r.status_code)
        return False, None
    if r.url is not infor_insc_turmas_url:
        logging.info("Navigate to subjects page failed. Relogin and retry")
        sucess, res = login(session)

    page = BeautifulSoup(r.text, 'html.parser')
    # TODO avisar caso LEI não se a primeira
    # quickfix

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


def extract_title_and_rows(zone: BeautifulSoup) -> Tuple[str, List[BeautifulSoup]]:
    zone_title = zone.find(class_="subtitle")
    if zone_title is not None:
        zone_title = zone_title.text.strip()
    if zone_title not in relevant_zone_titles:
        logging.info(f"{zone_title} title not in relevant zone titles. Skiping.")
        return zone_title, None
    logging.info(f"Zone title: {zone_title}")

    zone_content = zone.find(class_="zonecontent")
    zone_disp_table = zone.find(class_="displaytable")
    if zone_disp_table is None:
        text = re.sub(r'\s+', ' ', zone_content.text)
        logging.info(f"Zone table not found. Inside text: {text}")
        return zone_title, None

    zone_rows = zone_disp_table.find_all("tr")
    return zone_title, zone_rows


def get_subject_form(subject: Subject) -> BeautifulSoup:
    r = session.get(subject.url)
    if r.status_code != 200:
        return False

    page = BeautifulSoup(r.text, 'html.parser')
    form = page.find(id="listaInscricoesFormBean")
    if form is None:
        form = page.find(id="inscreverFormBean")
    if form is None:
        logging.error(
            f"Something went wrong. Cant find the enrolement form for {subject.name}")
        return None
    return form


def find_class_row(rows: List[BeautifulSoup], turma: str) -> BeautifulSoup:
    options = list(filter(lambda c: turma in c.text, rows))
    if not options:
        return None
    return options[0]


def gen_subject_configs(subjects: List[Subject], session: Session) -> bool:
    '''
    Generates the configuration file to be used for chosing the class.
    Returns True if no errors have occured, False otherwise.
    '''

    subjects_info = {}

    for subject in [s for s in subjects if s.url is not None]:
        logging.info(f"Subject: {subject.name}")
        info = {}
        info["last-updated"] = str(datetime.datetime.now())

        form = get_subject_form(subject)

        zones = form.find_all(class_="zone")

        for zone in zones:
            zone_title, zone_rows = extract_title_and_rows(zone)
            if zone_rows is None:
                continue
            if zone_title not in relevant_zone_titles:
                continue
            info[zone_title] = {"want": "ESCOLHE UMA OPCAO", "options": []}
            for row in zone_rows:
                zone_cols = row.find_all("td")
                if not zone_cols:
                    continue
                info[zone_title]["options"].append(
                    re.sub(r'\s+', ' ', zone_cols[0].text))
                row_text = "\t".join(re.sub(r'\s+', ' ', col.text)
                                     for col in zone_cols)
                logging.info("\t" + row_text)

        subjects_info[subject.name] = info
    with open(turmas_file_name, "w") as f:
        json.dump(subjects_info, f, sort_keys=True, indent=4)
    return True


def do_register(subjects: List[Subject], session: Session, time=5):
    try:
        turmas = json.load(open(turmas_file_name))
    except FileNotFoundError:
        logging.info(
            "turmas file file not found. Running gen_subject_configs first")
        gen_subject_configs(subjects, session)
        return do_register(subjects, session)
    except:
        raise

    payloads: Deque[Payload] = Deque()
    # Generate payloads
    for subject in [s for s in subjects if s.url is not None]:
        if subject.name not in turmas:
            continue
        form = get_subject_form(subject)
        form_url = infor_base_url + form['action']

        zones = form.find_all(class_="zone")

        for zone in zones:
            zone_title, zone_rows = extract_title_and_rows(zone)
            if zone_rows is None:
                continue
            turma = turmas[subject.name][zone_title]["want"]
            option = find_class_row(zone_rows, turma)
            if option is None:
                logging.info(
                    f"No option {turma} for {zone_title} in {subject.name}")
                continue

            inp = option.find(is_turma_tag)
            if inp is None:
                logging.info(
                    f"Something went wrong: {option.find_all('td')[-1].text.strip()}")
                # Extract input value from the horarios input
                value = option.find('input')['value']
                p = {"inscrever": value}
                payloads.append(Payload(subject, form_url, p, turma))
            else:
                vagas = option.find_all('td')[-3].text
                logging.info(f"You're in luck, a turma ainda tem {vagas}")
                p = {inp['name']: inp['value']}
                payloads.append(Payload(subject, form_url, p, turma))
            break

    logging.info(f"Payloads ready, number of payloads: {len(payloads)}.")

    while payloads:
        p = payloads.popleft()
        subject = p.subject
        form_url = p.form_url
        turma = p.turma
        payload = p.payload

        success, res = navigate_subjects_page(session)
        page = BeautifulSoup(res.text, 'html.parser')

        td = next(t for t in page.find_all(
            "td", {"class": "contentLeft"}) if subject.name in t.text).parent
        insc_url = td.find("a")["href"]
        session.get(infor_insc_turmas_base + insc_url)

        logging.info(f"Snnipping {subject.name} - {turma}")
        r = session.post(form_url, data=payload)
        if r.status_code != 200:
            logging.error("Something went wrong")
            continue
        if r.url == "https://inforestudante.uc.pt/nonio/inscturmas/listaInscricoes.do":
            # TODO: verificar se está de facto inscrito, pode ser que não há inscrições a decorrer.
            page = BeautifulSoup(r.text, 'html.parser')
            subjects_form = page.find(id="listaInscricoesFormBean")
            subjects_table_rows = subjects_form.find(
                class_="displaytable").tbody.find_all("tr")
            subject_row = next(
                r for r in subjects_table_rows if subject.name in r.text)
            if turma in subject_row.text:
                logging.info("Gotcha!")
                with open("success.log", "a") as f:
                    f.write(f"{subject.name}  -  {turma}")
                continue
            else:
                logging.info(f"Current: {subject_row.text}")
                turma_current = [
                    i for i in subject_row.text.strip().split("\n") if turma[:-1] in i]
                if turma_current:
                    turma_current = next(turma_current)
                    logging.info(
                        f"Not yet.. still in {turma_current}.")
                else:
                    #['01000068', 'Análise Matemática II\xa0*', '2.º Semestre', 'T1', '11-02-2021 13:00', '11-02-2021 23:49', 'Inscrições']
                    logging.info(f"Not yet.. inscrições a não estão a decorrer maybe?")
        elif r.url == "https://inforestudante.uc.pt/nonio/inscturmas/inscrever.do?method=submeter":
            logging.info("Not yet.. trying again")
            r = session.get(
                "https://inforestudante.uc.pt/nonio/inscturmas/listaInscricoes.do")
            r = session.get(subject.url)
        else:
            logging.error(
                "Something went wrong. Should not have been redirected here")
            # TODO recover and re-start process
        payloads.append(p)  # add to end of list
        sleep(time)

    logging.info("Done")


def log_status(r: Response, *args, **kwargs):
    logging.info(f"{r.request.method} {r.status_code} - {r.url}")


if __name__ == "__main__":
    # Username configuration
    config = load_configs()
    if config is None:
        exit()
    # Loggins configuration
    logging.basicConfig(
        format="%(asctime)s %(levelname)-8s %(message)s",
        level=logging.INFO,
        datefmt="%H:%M:%S")

    # Session configuration
    session = requests.Session()
    session.hooks['response'].append(log_status)

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
    #gen_subject_configs(subjects, session)
    do_register(subjects, session, 2)
