# coding: utf-8
import abc
import time
import string

import requests
import nltk.corpus

from lxml import html
from fuzzywuzzy import fuzz
from nltk.tokenize import wordpunct_tokenize
from collections import defaultdict, Counter


LINKS_FILE = 'links.txt'
USER_AGENT = ('Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 (KHTML, ' +
              'like Gecko) Chrome/41.0.2228.0 Safari/537.36')


class DataMiner(object):
    __metaclass__ = abc.ABCMeta

    def __init__(self, text):
        self.text = text
        self.parsed_text = html.fromstring(self.text)

    @abc.abstractmethod
    def get_name(self):
        pass

    @abc.abstractmethod
    def get_author(self):
        pass


class GooglePlay(DataMiner):
    def get_name(self):
        return self.parsed_text.xpath(
            '//*[@id="body-content"]/div[1]/div[1]/div/div[1]/div[2]/' +
            'div[1]/div/text()').pop()

    def get_author(self):
        return self.parsed_text.xpath(
            '//*[@id="body-content"]/div[1]/div[1]/div/div[1]/div[2]/' +
            'div[2]/a/span/text()').pop()


class AppleITunes(DataMiner):
    def get_name(self):
        return self.parsed_text.xpath(
            '//*[@id="title"]/div[1]/h1/text()').pop()

    def get_author(self):
        author = self.parsed_text.xpath(
            '//*[@id="title"]/div[1]/h2/text()').pop()
        author = author.replace('By ', '')
        return author


class WindowsPhone(DataMiner):
    def get_name(self):
        return self.parsed_text.xpath('//*[@id="application"]/h1/text()').pop()

    def get_author(self):
        return self.parsed_text.xpath('//*[@id="publisher"]/a/text()').pop()


class Product(object):
    def __init__(self, name, links=None):
        self.name = name
        if links is None:
            self.links = []
        else:
            self.links = links

    def extend(self, links):
        self.links.extend(links)

    def __str__(self):
        return self.name


def almost_similar(str0, str1, threshold=60):
    """
    Определяет, похожи ли строки по порогу
    :param str0:
    :param str1:
    :return:
    """
    return fuzz.partial_ratio(str0, str1) >= threshold


if __name__ == '__main__':
    products = defaultdict(list)
    stopwords = nltk.corpus.stopwords.words('english')

    with open(LINKS_FILE) as f:
        for url in f.readlines():
            url = url.rstrip('\n')
            try:
                headers = {'user-agent': USER_AGENT}
                req = requests.get(url, timeout=3, headers=headers)
            except requests.RequestException:
                print 'Failed to get url: %s' % url
                continue

            data_miner = None
            if 'play.google' in url:
                data_miner = GooglePlay(text=req.text)
            elif 'itunes.apple' in url:
                data_miner = AppleITunes(text=req.text)
            elif 'windowsphone' in url:
                data_miner = WindowsPhone(text=req.text)
            else:
                print 'Unknown data source'
                continue

            name = data_miner.get_name()
            author = data_miner.get_author()

            # Токенизируем имя, удаляем стоп-слова, пунктуацию
            #  и пустые строки
            name_tokenized = []
            for token in wordpunct_tokenize(name):
                token = token.strip(string.punctuation)
                if token not in stopwords and token != '':
                    name_tokenized.append(token)

            """
                {
                    (name, author): links
                }
            """
            prod_key = (' '.join(name_tokenized[:2]), author)
            products[prod_key].append(url)
            time.sleep(0.5)

    # Финальный список продуктов
    final_products = []

    # Выберем дубликаты имен продуктов
    duplicated_names = [x for x, y in
                        Counter([d[0] for d in products]).items() if y > 1]

    # проверим дубликаты на различных авторов через нечеткий поиск
    temp_duplicates = {}  # {skype_qik, skype: links}
    for dup in duplicated_names:
        for pkey in products:
            if pkey[0] == dup:
                temp_duplicates[pkey] = products[pkey]

    previous_dup_index = None
    result = {}
    for dup_index in sorted(temp_duplicates, key=lambda k: k[0]):
        if not previous_dup_index:
            result[dup_index] = temp_duplicates[dup_index]
            previous_dup_index = dup_index
        else:
            if dup_index[0] == previous_dup_index[0] and almost_similar(
                    dup_index[1], previous_dup_index[1]):
                result[previous_dup_index].extend(temp_duplicates[dup_index])
            else:
                result[dup_index] = temp_duplicates[dup_index]
                previous_dup_index = dup_index

    for r in result:
        product = Product(name=r[0], links=result[r])
        final_products.append(product)
        # remove that records from data
        for prod in dict(products):
            if prod[0] == r[0]:
                del products[prod]

    # Проверим похожесть остальных имен, среди похожих выберем
    # самое короткое имя
    shortest_previous_index = None
    shortest_name = u''
    result = {}
    for index in products:
        if not shortest_previous_index:
            result[index] = products[index]
            shortest_previous_index = index
        else:
            if almost_similar(index[0],
                              shortest_previous_index[0]) and almost_similar(
                    index[1], shortest_previous_index[1]):
                if len(index[0]) < len(shortest_previous_index[0]):
                    tmp_links = result[shortest_previous_index]
                    del result[shortest_previous_index]
                    shortest_previous_index = index
                    result[
                        shortest_previous_index] = tmp_links + products[index]
                else:
                    result[shortest_previous_index].extend(products[index])
            else:
                result[index] = products[index]
                shortest_previous_index = index

    for r in result:
        product = Product(name=r[0], links=result[r])
        final_products.append(product)

    for fp in sorted(final_products, key=lambda f: f.name):
        print fp.name