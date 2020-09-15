from genericpath import exists
import urllib3
import urllib
import json
from bs4 import BeautifulSoup
import time
import os
from urllib3 import request

from urllib3.util.url import Url

infor_base_url = "https://inforestudante.uc.pt"
infor_url = "https://inforestudante.uc.pt/nonio/security/login.do"

form_data = {"username": "", "password": ""}
excude_years = ["2015/2016", "2016/2017"]


def saca_disciplinas(page: BeautifulSoup, path):

    detalhes_buttons = page.find_all(class_="botaodetalhes")

    for button in detalhes_buttons:
        name = button.parent.parent.contents[1].text  # 0 is newline

        r = http.request(
            'GET', "https://inforestudante.uc.pt/nonio/pautas/"+button['href'], headers=headers)

        print(f"GET {name} status: {r.status}")
        if r.status != 200:
            continue

        if not os.path.isdir(path):
            os.makedirs(path, exist_ok=True)
        with open(f"{path}/{name}.html", "w") as f:
            f.write(r.data.decode())


if __name__ == "__main__":
    http = urllib3.PoolManager()

    # GET infor page
    r = http.request('GET', infor_url)
    print(f"GET {infor_url}, status: {r.status}")
    if r.status != 200:
        exit()

    page = BeautifulSoup(r.data, 'html.parser')
    cookie = r.headers["Set-Cookie"].split()[0]
    headers = {"Cookie": cookie}

    login_form = page.find(id="loginFormBean")
    action = login_form["action"]

    login_url = infor_base_url+action

    # POST login attempt

    r = http.request('POST', login_url, fields=form_data, retries=5)

    print(f"POST Login request status: {r.status}")
    if r.status != 200:
        exit()

    # GET pautas
    page = BeautifulSoup(r.data, 'html.parser')
    m = page.find(class_="menu_30")
    pautas_url = urllib.parse.urljoin(
        "https://inforestudante.uc.pt/nonio/dashboard/dashboard.do", m.parent['href'])

    r = http.request('GET', pautas_url, headers=headers)
    print(f"GET {pautas_url} status: {r.status}")
    if r.status != 200:
        exit()

    # for each year
    page = BeautifulSoup(r.data, 'html.parser')
    tr = page.find(id="linhaAnoLectivoMinhasUc")
    select = tr.contents[3].contents[1]
    options = select.find_all("option")

    selected = select.find(selected="selected")
    year = selected["value"]

    next_arg = select["onchange"].split("'")[1]
    next_url = "https://inforestudante.uc.pt/nonio/pautas/"+next_arg

    path = f"./pautas/{year.replace('/','-')}"

    saca_disciplinas(page, path)

    # download other years
    for option in options[1:]:
        ano = option["value"]
        if ano in excude_years:
            continue
        r = http.request("POST", next_url, headers=headers, fields={
                         "anoLectivoMinhasUCSeleccionado": ano})
        print(f"GET ano {ano} status: {r.status}")
        if r.status != 200:
            exit()

        page = BeautifulSoup(r.data, 'html.parser')
        tr = page.find(id="linhaAnoLectivoMinhasUc")
        select = tr.contents[3].contents[1]

        selected = select.find(selected="selected")
        year = selected["value"]

        next_arg = select["onchange"].split("'")[1]
        next_url = "https://inforestudante.uc.pt/nonio/pautas/"+next_arg

        path = f"./pautas/{year.replace('/','-')}"

        saca_disciplinas(page, path)
