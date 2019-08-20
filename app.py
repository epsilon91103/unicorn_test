import asyncio
import logging
import itertools
import argparse
import json

from aiohttp import ClientSession, web

from class_service import BaseService

logging.basicConfig(
    level=logging.DEBUG,
    format='%(filename)s[LINE:%(lineno)d]# %(levelname)-8s [%(asctime)s]  %(message)s'
)

HOST = '127.0.0.1'
PORT = 8080
# ссылка на ресурс для получения валют
URL = 'https://www.cbr-xml-daily.ru/daily_json.js'
# список валют для сервиса
CODE_CURRENCIES = ('RUB', 'USD', 'EUR')
# множество положительных значений debug для его активации
DEBUG_TRUE_VALUES = frozenset(('1', 'True', 'true', 'y', 'Y'))
# период сна информирующего метода сервиса (секунд)
SLEEP_INFO_METHOD = 60
# период сна метода парсинга (минут)
SLEEP_PARS_METHOD = 5


class Service(BaseService):
    def __init__(self, arguments, code_currencies=None):
        self.code_currencies = CODE_CURRENCIES if code_currencies is None else code_currencies
        self.currencies = dict.fromkeys(self.code_currencies)
        if 'RUB' in self.currencies:
            self.currencies['RUB'] = 1
        self.currency_amount = dict.fromkeys(self.code_currencies)
        self.total_amount = dict.fromkeys(self.code_currencies)
        self.currency_ratio = dict.fromkeys('%s-%s' % currs for currs in itertools.combinations(self.currencies, 2))
        self.debug_mode = arguments.debug in DEBUG_TRUE_VALUES
        self.msg = None
        self.close_service = False
        for curr in CODE_CURRENCIES:
            self.currency_amount[curr] = vars(arguments)[curr.lower()]
        self.n = arguments.period * 60

    # генерация сообщения по валютам
    def create_message(self):
        self.msg = '\n\n'.join(
            map(
                self.get_str_dict,
                (self.currency_amount, self.currency_ratio, self.total_amount)
            )
        )

    # пересчет общего объема денежных средств
    def calculate_total_amount(self):
        try:
            rub_amount = sum(self.currency_amount[key] * self.currencies[key] for key in self.code_currencies)
            for currency in self.code_currencies:
                self.total_amount[currency] = rub_amount / self.currencies[currency]
            logging.info('Total amount successfully recounted')
        except TypeError:
            logging.warning('Unable to get total cash currencies')

    # пересчет соотношения между валютами
    def calculate_currency_ratio(self):
        try:
            for l_curr, r_curr in itertools.combinations(self.currencies, 2):
                self.currency_ratio['{}-{}'.format(l_curr, r_curr)] = self.currencies[r_curr] / self.currencies[l_curr]
            logging.info('Currency ratio successfully recounted')
        except TypeError:
            logging.warning('Unable to get currency ratio')

    # получение и обработка новых данных по валютам
    async def parse_currencies(self):
        async with ClientSession() as session:
            while not self.close_service:
                try:
                    # получаем новые данные
                    async with session.get(URL) as response:
                        if self.debug_mode:
                            logging.info('Response %s' % response)
                        page = await response.read()
                    logging.info('Currency data successfully received')
                except Exception as err:
                    logging.error('Error in receiving currencies: {}'.format(err))
                else:
                    try:
                        curr_rate = json.loads(page)['Valute']

                        old_currencies = self.currencies.copy()
                        # обновляем курс валют в атрибуте
                        self.currencies.update((curr, curr_rate[curr]['Value'])
                                               for curr in self.code_currencies if curr != 'RUB')

                        # проверяем наличие изменений по валютам
                        if self.currencies != old_currencies:
                            self.calculate_currency_ratio()
                            self.calculate_total_amount()
                        else:
                            logging.info('The exchange rate has not changed')
                        logging.info('Currency data processed successfully')
                    except Exception as err:
                        logging.error('Error processing data: {}'.format(err))

                await asyncio.sleep(self.n)

    # вывод информации по валютам
    async def print_currency(self):
        last_currencies = self.currencies.copy()
        last_amount = self.currency_amount.copy()
        while not self.close_service:
            # проверка наличия изменений по валютам
            if last_currencies != self.currencies or last_amount != self.currency_amount:
                last_currencies = self.currencies.copy()
                last_amount = self.currency_amount.copy()
                self.create_message()
                print(self.msg)
                logging.debug('Updated information is displayed in the console')
            await asyncio.sleep(SLEEP_INFO_METHOD)

    # реализация обработки гет метода
    async def get_handler(self, request):
        code = request.match_info.get('valute')

        if code is None:
            if self.debug_mode:
                logging.info('Request a nonexistent page')
            return web.Response(status=404)

        code = code.upper()
        answ = text_debug = ''
        if code in self.code_currencies:
            text_debug = 'Currency request {}'.format(code)
            answ = "{}: {}".format(code, self.currencies[code])
        elif code == 'AMOUNT':
            self.create_message()
            text_debug = 'Request for information on all currencies'
            answ = self.msg

        if self.debug_mode:
            logging.info(text_debug)

        return web.Response(
            text=answ,
            content_type='text/plain'
        )

    # реализация обработки post метода modify
    async def post_handler(self, request):
        data = await request.post()
        path = request.path
        update = False

        for key in data:
            try:
                key_up = key.upper()
                if key_up in self.currency_amount:
                    if path == '/modify':
                        self.currency_amount[key_up] += float(data[key])
                    elif path == '/amount/set':
                        self.currency_amount[key_up] = float(data[key])
                    update = True
            except Exception as err:
                logging.debug('Invalid currency code {}: {}'.format(key, err))

        if update:
            self.calculate_currency_ratio()
            self.calculate_total_amount()
            text = 'Changes successfully accepted'
        else:
            text = 'No changes applied'

        return web.Response(
            text=text,
            content_type='text/plain'
        )

    # запуск сервиса
    def start_service(self):
        logging.debug('Start application')
        if self.debug_mode:
            logging.debug('Debug mode enabled')

        loop = asyncio.get_event_loop()

        loop.create_task(self.parse_currencies())
        loop.create_task(self.print_currency())

        app = web.Application()
        app.router.add_get('/{valute}/get', self.get_handler)
        app.router.add_post('/amount/set', self.post_handler)
        app.router.add_post('/modify', self.post_handler)

        if self.debug_mode:
            web.run_app(app, host=HOST, port=PORT)
        else:
            web.run_app(app, host=HOST, port=PORT, access_log=None)

        loop.run_forever()
        loop.close()

        logging.debug('Application shutdown')

    # генерация текстового представления словаря
    @staticmethod
    def get_str_dict(my_dict):
        return '\n'.join('{}: {}'.format(key.lower(), val) for key, val in my_dict.items())


# обработка аргументов
def parse_args():
    """
    Processing arguments
    :return:
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--period',
        type=int,
        default=SLEEP_PARS_METHOD,
        help='Exchange Rate Query Frequency',
    )
    parser.add_argument(
        '--debug',
        type=str,
        default='False',
        help='Debug mode',
    )
    # получение курса валют из входных аргументов
    for curr in CODE_CURRENCIES:
        parser.add_argument(
            '--{}'.format(curr.lower()),
            type=float,
            default=0,
            help='Amount of currency {}'.format(curr)
        )
    return parser.parse_known_args()


if __name__ == '__main__':
    (input_args, unknown_args) = parse_args()
    service = Service(input_args)
    service.start_service()
