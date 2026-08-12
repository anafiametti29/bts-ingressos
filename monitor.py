import os
import re
import json
import html
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]

PAGINA_DATAS = "https://buyticketbrasil.com/datas/bts%E2%80%932026worldtourarirang"

PRECO_MAXIMO = 100000  # R$ 1.000,00 em centavos

EXCLUIR = [
    "pcd",
    "idoso",
    "professor",
    "acompanhante",
    "aposentado",
]

STATE_FILE = "estado.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    )
}


def enviar_telegram(mensagem):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    resposta = requests.post(
        url,
        data={
            "chat_id": CHAT_ID,
            "text": mensagem,
            "disable_web_page_preview": False,
        },
        timeout=30,
    )

    resposta.raise_for_status()


def baixar(url):
    resposta = requests.get(
        url,
        headers=HEADERS,
        timeout=30,
    )

    resposta.raise_for_status()
    return resposta.text


def encontrar_paginas_eventos():
    texto = baixar(PAGINA_DATAS)

    soup = BeautifulSoup(texto, "html.parser")

    urls = set()

    for link in soup.find_all("a", href=True):
        href = link["href"]

        if "/evento/" not in href:
            continue

        if "bts" not in href.lower():
            continue

        url = urljoin(PAGINA_DATAS, href)
        urls.add(url)

    return sorted(urls)


def normalizar_html(texto):
    texto = html.unescape(texto)

    # O JSON do Next.js aparece escapado dentro do HTML.
    texto = texto.replace('\\"', '"')
    texto = texto.replace("\\/", "/")

    return texto


def obter_data_evento(texto):
    texto = normalizar_html(texto)

    match = re.search(
        r'"data":\{"iso":"([^"]+)"',
        texto
    )

    if not match:
        return "Data não identificada"

    iso = match.group(1)

    try:
        data = iso[:10]
        ano, mes, dia = data.split("-")

        # O horário do site pode aparecer convertido para UTC.
        return f"{dia}/{mes}/{ano}"
    except Exception:
        return iso


def extrair_ingressos(texto, url_evento):
    texto = normalizar_html(texto)

    data_evento = obter_data_evento(texto)

    padrao = re.compile(
        r'"([^"]+)\|\|([^"]+)":\{'
        r'"preco_min":(\d+),'
        r'"disponivel":(\d+),'
        r'"id_ref":"([^"]+)"'
    )

    ingressos = []

    for match in padrao.finditer(texto):
        setor = match.group(1).strip()
        categoria = match.group(2).strip()
        preco = int(match.group(3))
        quantidade = int(match.group(4))
        id_ref = match.group(5)

        ingressos.append({
            "data": data_evento,
            "setor": setor,
            "categoria": categoria,
            "preco": preco,
            "quantidade": quantidade,
            "id_ref": id_ref,
            "url": url_evento,
        })

    return ingressos


def deve_ignorar(ingresso):
    categoria = ingresso["categoria"].lower()

    for palavra in EXCLUIR:
        if palavra in categoria:
            return True

    return False


def ingresso_interessa(ingresso):
    if ingresso["quantidade"] <= 0:
        return False

    if ingresso["preco"] <= 0:
        return False

    if ingresso["preco"] > PRECO_MAXIMO:
        return False

    if deve_ignorar(ingresso):
        return False

    return True


def chave_ingresso(ingresso):
    return (
        f'{ingresso["data"]}|'
        f'{ingresso["setor"]}|'
        f'{ingresso["categoria"]}'
    )


def carregar_estado():
    if not os.path.exists(STATE_FILE):
        return {}

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as arquivo:
            return json.load(arquivo)
    except Exception:
        return {}


def salvar_estado(estado):
    with open(STATE_FILE, "w", encoding="utf-8") as arquivo:
        json.dump(
            estado,
            arquivo,
            ensure_ascii=False,
            indent=2,
        )


def formatar_preco(valor_centavos):
    valor = valor_centavos / 100

    return (
        f"R$ {valor:,.2f}"
        .replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
    )


def main():
    estado_anterior = carregar_estado()
    estado_atual = {}

    paginas = encontrar_paginas_eventos()

    if not paginas:
        raise RuntimeError(
            "Nenhuma página de evento do BTS foi encontrada."
        )

    total_lidos = 0

    for url_evento in paginas:
        texto = baixar(url_evento)
        ingressos = extrair_ingressos(texto, url_evento)

        total_lidos += len(ingressos)

        for ingresso in ingressos:
            chave = chave_ingresso(ingresso)

            estado_atual[chave] = {
                "preco": ingresso["preco"],
                "quantidade": ingresso["quantidade"],
                "id_ref": ingresso["id_ref"],
            }

            if not ingresso_interessa(ingresso):
                continue

            anterior = estado_anterior.get(chave)

            deve_alertar = False
            motivo = ""

            if anterior is None:
                deve_alertar = True
                motivo = "Ingresso dentro do seu limite apareceu"

            else:
                preco_anterior = anterior.get("preco", 999999999)
                quantidade_anterior = anterior.get("quantidade", 0)

                if preco_anterior > PRECO_MAXIMO:
                    deve_alertar = True
                    motivo = "O preço caiu para até R$ 1.000"

                elif ingresso["preco"] < preco_anterior:
                    deve_alertar = True
                    motivo = "O preço diminuiu"

                elif ingresso["quantidade"] > quantidade_anterior:
                    deve_alertar = True
                    motivo = "Entraram novos ingressos"

            if deve_alertar:
                mensagem = (
                    "🚨 BTS — INGRESSO ENCONTRADO!\n\n"
                    f"📅 Data: {ingresso['data']}\n"
                    f"🎟 Setor: {ingresso['setor']}\n"
                    f"👤 Categoria: {ingresso['categoria']}\n"
                    f"💰 Preço: {formatar_preco(ingresso['preco'])}\n"
                    f"🎫 Disponíveis: {ingresso['quantidade']}\n\n"
                    f"⚡ {motivo}\n\n"
                    "👉 COMPRAR AGORA:\n"
                    f"{ingresso['url']}"
                )

                enviar_telegram(mensagem)

    salvar_estado(estado_atual)

    print(f"Páginas verificadas: {len(paginas)}")
    print(f"Combinações de ingressos lidas: {total_lidos}")
    print("Monitoramento concluído com sucesso.")


if __name__ == "__main__":
    main()
