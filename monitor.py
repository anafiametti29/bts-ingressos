import os
import json
import requests
from bs4 import BeautifulSoup

URL = "https://bts.buyticketbrasil.com/"

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]

STATE_FILE = "estado.json"


def enviar_telegram(mensagem):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    dados = {
        "chat_id": CHAT_ID,
        "text": mensagem,
        "disable_web_page_preview": False
    }

    resposta = requests.post(url, data=dados, timeout=30)
    resposta.raise_for_status()


def buscar_ingressos():
    resposta = requests.get(
        URL,
        headers={
            "User-Agent": "Mozilla/5.0"
        },
        timeout=30
    )

    resposta.raise_for_status()

    soup = BeautifulSoup(resposta.text, "html.parser")

    texto = soup.get_text(" ", strip=True)

    return texto


def carregar_estado():
    if not os.path.exists(STATE_FILE):
        return None

    with open(STATE_FILE, "r", encoding="utf-8") as arquivo:
        return json.load(arquivo)


def salvar_estado(texto):
    with open(STATE_FILE, "w", encoding="utf-8") as arquivo:
        json.dump({"texto": texto}, arquivo, ensure_ascii=False)


def main():
    texto_atual = buscar_ingressos()
    estado_anterior = carregar_estado()

    if estado_anterior is None:
        salvar_estado(texto_atual)

        enviar_telegram(
            "🤖 BOT BTS ATIVADO!\n\n"
            "O monitoramento da BuyTicket começou com sucesso.\n\n"
            "Vou te avisar quando detectar uma alteração nos ingressos."
        )

        return

    texto_anterior = estado_anterior["texto"]

    if texto_atual != texto_anterior:

        enviar_telegram(
            "🚨 ALTERAÇÃO NOS INGRESSOS DO BTS!\n\n"
            "A página da BuyTicket mudou.\n\n"
            "Confira imediatamente:\n"
            f"{URL}"
        )

        salvar_estado(texto_atual)


if __name__ == "__main__":
    main()
