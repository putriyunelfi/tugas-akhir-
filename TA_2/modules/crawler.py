import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
import urllib.robotparser
from nltk.corpus import wordnet
from nltk import word_tokenize, pos_tag
from nltk.stem import WordNetLemmatizer
import datetime
from url_normalize import url_normalize
import time
import string
import collections


proxies = {
    'http': 'socks5h://127.0.0.1:9050',
    'https': 'socks5h://127.0.0.1:9050'
}

# global list for errors
errors = []


# class to implement priority queue
# the queue contains items in the format: [page_promise, url]
class PriorityQueue:

    def __init__(self):
        self.queue = []

    # find the index at which the new item will be stored
    # (using binary search)
    # descending order of page_promise is used
    def calculate_index(self, item, start, end):
        if len(self.queue) > 0:
            if start < end:
                index = int((start + end) / 2)
                if item[0] == self.queue[index][0]:
                    return index
                elif item[0] > self.queue[index][0]:
                    return self.calculate_index(item, start, index - 1)
                elif item[0] < self.queue[index][0]:
                    return self.calculate_index(item, index + 1, end)
            elif start == end:
                if end != len(self.queue):
                    if item[0] > self.queue[start][0]:
                        return start
                    else:
                        return start + 1
                else:
                    if item[0] < self.queue[end - 1][0]:
                        return end
                    else:
                        return end - 1
            else:
                return start
        else:
            return start

    # display the contents of the queue.
    def display_queue(self):
        print("Queue:")
        for item in self.queue:
            print(item)

    # add an item to the queue
    def enqueue(self, item):

        if item not in self.queue:
            index = self.calculate_index(item, 0, len(self.queue))  # calculate index for new element
            self.queue.insert(index, item)  # insert element at index

    # pop an item from the queue
    def dequeue(self):

        # while len(self.queue) <= 0:
        #     continue

        item = self.queue[0]  # item with highest promise
        del self.queue[0]  # remove item from the queue
        return item

    # Returns the size of the queue
    def get_size(self):
        return len(self.queue)

    # delete the item from the queue
    def delete(self, index):
        item = self.queue[index]
        del self.queue[index]  # delete item at index
        return item

    # find a url in the queue
    def find(self, url):
        i = -1

        for index in range(len(self.queue)):
            if self.queue[index][1] == url:
                i = index
        return i

    # update the promise of a url if it is found while parsing another page
    def update_queue(self, url, parent_relevance):

        index = self.find(url)
        if index != -1:
            item = self.queue[index]
            del self.queue[index]  # remove item from queue
            item[0] += 0.25 * parent_relevance  # update promise

            # index = self.calculate_index(item, 0, len(self.queue))  # compute new index for item
            # self.queue.insert(index, item)  # insert at index
            self.enqueue(item)  # recompute the index (using the updated promise) and insert item at index


# class to implement the parsed_urls dictionary
# the dictionary has visited urls as keys and values as a list of [links_found, promise, len, time]
# links_found are the links found while parsing the page
# promise is the page relevance promise
# len is the page length
# time is the time at which the page was parsed
class ParsedURLs:
    def __init__(self):
        self.parsed_urls = collections.OrderedDict()  # to remember the order in which URLs (keys) were added

    def add_item(self, url, links_found, promise, relevance, len, status_code, time):  # add an item into the dictionary
        self.parsed_urls[url] = [links_found, promise, relevance, len, status_code, time]

    def find(self, url):  # check if item already exists
        return url in self.parsed_urls

    def display(self):  # display URLs in dictionary i.e. the keys
        print(self.parsed_urls.keys())

    def get_keys(self):  # return all the keys of the dictionary
        return self.parsed_urls.keys()

    def get_item(self, key):  # return the number of links found, promise, page len, timestamp for a given key
        return len(self.parsed_urls[key][0]), self.parsed_urls[key][1], self.parsed_urls[key][2], \
               self.parsed_urls[key][3], self.parsed_urls[key][4], self.parsed_urls[key][5]


# class to keep track of page count i.e. number of pages crawled
class PageCount:
    def __init__(self):
        self.page_num = 0

    def increment(self):
        self.page_num += 1

    def get_page_num(self):
        return self.page_num


page_count = PageCount()


# class to perform multi-threaded crawling
class Crawler:
    def __init__(self, links_to_parse, parsed_urls, query, pages, page_link_limit, mode, synonyms_list, lemmatized_words):
        # initializing all the attributes
        self.links_to_parse = links_to_parse
        self.parsed_urls = parsed_urls
        self.query = query
        self.pages = pages
        self.page_link_limit = page_link_limit
        self.mode = mode
        self.synonyms_list = synonyms_list
        self.lemmatized_words = lemmatized_words

    def run(self):
        item = self.links_to_parse.dequeue()  # get first item (highest promise) from the queue, item = [promise,url]
        print('Dequeued: ', item)
        url = item[1]
        if validate_link(url):  # after link is dequeued, check if it can be crawled i.e. status code, robots, MIME type
            html_text, links = visit_url(url, self.page_link_limit)  # read the HTML content of the URL, extract links
            while (html_text, links) == (None, None):  # keep trying till visit_url() returns non-None values
                item = self.links_to_parse.dequeue()
                url = item[1]
                if validate_link(url):
                    html_text, links = visit_url(url, self.page_link_limit)

            page_count.increment()  # increment the page counter
            print(page_count.get_page_num())

            # get relevance of a URL after visiting it
            relevance = get_relevance(html_text, self.query, self.synonyms_list, self.lemmatized_words)
            # will use it to compute promise of its child links

            # add the crawled URL and details into the dictionary parsed_urls
            self.parsed_urls.add_item(url, links, item[0], relevance, len(html_text), requests.get(url, proxies=proxies).status_code,
                                      str(datetime.datetime.now().time()))
            print('Parsed: ', item)
            print('Relevance: ' + str(relevance) + '\n')

            for index in range(len(links)):  # add all the links present in the page to the queue
                if links[index] in self.parsed_urls.get_keys():  # if URL was already parsed earlier, continue
                    continue
                else:  # URL not parsed before
                    id = self.links_to_parse.find(links[index])  # check if the URL is already present in the queue
                    if id != -1:
                        # for focused crawling, update the promise of the link using parent's relevance
                        # update item, pass parent relevance
                        self.links_to_parse.update_queue(links[index], relevance)
                    else:
                        # URL not in the queue
                        if pre_validate_link(links[index]):  # pre-validate before enqueue, validate upon dequeue
                            promise = get_promise(self.query, links[index], self.mode, relevance, self.synonyms_list,
                                                  self.lemmatized_words)
                            # 'relevance' is of parent
                            new_item = [promise, links[index]]
                            self.links_to_parse.enqueue(new_item)


def get_start_pages(query, num_start_pages=10):
    """ get start pages by performing a Google search """
#error
    res = requests.get('http://6nhmgdpnyoljh5uzr5kwlatx2u3diou4ldeommfxjz3wkhalzgjqxzqd.onion/', params={'q': query}, proxies=proxies) #memasukkan url yang akan di crawl # akses links.txt dari hasil github agus
    soup = BeautifulSoup(res.content, 'lxml')
    links = soup.find_all('a')

    initial_links = []
    count = 0

    connecttor()

    for link in links:
        href = link.get('href')
        if "url?q=" in href and "webcache" not in href:
            l_new = href.split("?q=")[1].split("&sa=U")[0]
            if pre_validate_link(url_normalize(l_new)):  # pre-validating link before enqueue, but validate upon dequeue
                count += 1
                if count <= num_start_pages:
                    initial_links.append(url_normalize(l_new))
                else:
                    break
    return list(set(initial_links))


def pre_validate_link(url):
    """ only checks if the link contains excluded words and/or types """

    excluded_words = ['download', 'upload', 'javascript', 'cgi', 'file']
    excluded_types = [".asx", ".avi", ".bmp", ".css", ".doc", ".docx",
                      ".flv", ".gif", ".jpeg", ".jpg", ".mid", ".mov",
                      ".mp3", ".ogg", ".pdf", ".png", ".ppt", ".ra",
                      ".ram", ".rm", ".swf", ".txt ", ".wav", ".wma",
                      ".wmv", ".xml", ".zip", ".m4a", ".m4v", ".mov",
                      ".mp4", ".m4b", ".cgi", ".svg", ".ogv", ".dmg", ".tar", ".gz"]

    for ex_word in excluded_words:
        if ex_word in url.lower():
            errors.append('Link contains excluded terms')
            return False

    for ex_type in excluded_types:
        if ex_type in url.lower():
            errors.append('Link contains excluded type')
            return False

    return True


def validate_link(url):
    """ checks if website is crawlable (status code 200) and if its robots.txt allows crawling
    also checks for the MIME type returned in the response header """

    # checking if the url returns a status code 200
    try:
        r = requests.get(url, proxies=proxies)
        if r.status_code == 200:
            pass  # website returns status code 200, so check for robots.txt
        else:
            print(url, r.status_code, 'failed')
            errors.append(r.status_code)
            return False
    except:
        print(url, 'request failed')  # request failed
        errors.append('Request Failed')
        return False

    # checking if the website has a robots.txt, and then checking if I am allowed to crawl it
    domain = urlparse(url).scheme + '://' + urlparse(url).netloc

    try:
        rp = urllib.robotparser.RobotFileParser()
        rp.set_url(domain + '/robots.txt')
        rp.read()
        if not rp.can_fetch('*', url):  # robots.txt mentions that the link should not be parsed
            print('robots.txt does not allow to crawl', url)
            errors.append('Robots Exclusion')
            return False
    except:
        return False

    # checking the MIME type returned in the response header
    try:
        if 'text/html' not in r.headers['Content-Type']:
            errors.append('Invalid MIME type')
            return False
    except:
        errors.append('Request Failed')
        return False
    return True


def get_input():
    """ get query, number of start pages, number of pages to be returned and mode """

    query = input('Enter your query : ').strip()
    num_start_pages = input("Enter the number of start pages : ").strip()
    n = input("Enter the number of pages to be returned : ").strip()
    page_link_limit = input("Enter the max. no. of links to be fetched from each page : ")\
        .strip()
    mode = input("Enter mode : ").strip()
    relevance_threshold = input('Enter the relevance threshold : ').strip()

    print('\nObtaining start pages...\n')
    # checking if values are input correctly, otherwise use defaults
    if len(query) == 0:
        query = 'wildfires california'

    if len(num_start_pages) == 0 or int(num_start_pages) <= 0:
        num_start_pages = 10

    if len(n) == 0 or int(n) < 10:
        n = 1000

    if len(page_link_limit) == 0 or int(page_link_limit) < 10:
        page_link_limit = 25

    if len(mode) == 0 or mode.lower() not in {'focused'}:
        mode = 'focused'

    if len(relevance_threshold) == 0 or (int(relevance_threshold) < 0 or int(relevance_threshold) > 4.75):
        relevance_threshold = 1

    return query, int(num_start_pages), int(n), int(page_link_limit), mode, int(relevance_threshold)


def get_promise(query, url, mode, parent_relevance, synonyms_list, lemmatized_words):
    """ returns the promise of a URL, based on which URLs are placed on the priority queue """
    if mode.lower() == 'focused':
        return 1  # all pages have the same promise in a simple focused crawl since we do not compute relevance
    else:
        # calculate promise based on the link
        promise = 0

        # remove punctuation from query
        punctuation = set(string.punctuation)
        query = ''.join(x for x in query if x not in punctuation)

        query_terms = [q.lower() for q in query.strip().split()]

        # checking if all or any of the terms are in the link, if synonyms are present, if lemmatized words are present

        if all([x in url.lower() for x in query_terms]):  # all query terms are in the URL
            promise += 0.5
        elif any([x in url.lower() for x in query_terms]):  # at least 1 query term in URL, but not all
            promise += 0.25
        else:  # no query term in URL
            pass  # keep promise as is

        # checking for synonyms
        if all([x in url.lower() for x in synonyms_list]):  # all synonyms are in the URL
            promise += 0.4
        elif any([x in url.lower() for x in synonyms_list]):  # at least 1 synonym is in URL, but not all
            promise += 0.2
        else:  # no synonym in URL
            pass  # keep promise as is

        # checking for lemmatized words
        if all([x in url.lower() for x in lemmatized_words]):  # all lemmatized words are in the URL
            promise += 0.4
        elif any([x in url.lower() for x in lemmatized_words]):  # at least 1 lemmatized word is in URL, but not all
            promise += 0.2
        else:  # no lemmatized word in URL
            pass  # keep promise as is

        promise += 0.25 * parent_relevance  # giving a certain weight to URL's parent's relevance
        promise /= len(url)  # to penalize longer URLs
        return promise


def get_relevance(html_text, query, synonyms_list, lemmatized_words):
    """ returns the relevance of a page after crawling it """

    # remove punctuation from query
    punctuation = set(string.punctuation)
    query = ''.join(x for x in query if x not in punctuation)

    query_terms = query.lower().strip().split()
    relevance = 0

    soup = BeautifulSoup(html_text, 'lxml')

    if soup.title:
        # TITLE
        title = soup.title.text.lower()
        # checking query terms -----------------------------------------
        if all([q in title for q in query_terms]):  # all terms in title
            relevance += 0.25
        elif any([q in title for q in query_terms]):  # at least one term in title but not all
            relevance += 0.15
        else:
            pass  # keep relevance as is

        # checking synonyms_list terms ----------------------------------
        if all([q in title for q in synonyms_list]):  # all terms in title
            relevance += 0.2
        elif any([q in title for q in synonyms_list]):  # at least one term in title but not all
            relevance += 0.1
        else:
            pass  # keep relevance as is

        # checking lemmatized words -----------------------------------------
        if all([q in title for q in lemmatized_words]):  # all terms in title
            relevance += 0.2
        elif any([q in title for q in lemmatized_words]):  # at least one term in title but not all
            relevance += 0.1
        else:
            pass  # keep relevance as is

    if soup.find('h1'):
        # FIRST HEADING
        h1 = soup.find('h1').text.lower()  # first h1 heading

        # checking query terms -----------------------------------------
        if all([q in h1 for q in query_terms]):  # all terms in first heading
            relevance += 0.5
        elif any([q in h1 for q in query_terms]):  # at least one term in heading but not all
            relevance += 0.45
        else:
            pass  # keep relevance as is

        # checking synonyms_list terms ----------------------------------
        if all([q in h1 for q in synonyms_list]):  # all terms in first heading
            relevance += 0.45
        elif any([q in h1 for q in synonyms_list]):  # at least one term in heading but not all
            relevance += 0.4
        else:
            pass  # keep relevance as is

        # checking lemmatized words -----------------------------------------
        if all([q in h1 for q in lemmatized_words]):  # all terms in first heading
            relevance += 0.45
        elif any([q in h1 for q in lemmatized_words]):  # at least one term in heading but not all
            relevance += 0.4
        else:
            pass  # keep relevance as is

    if soup.find_all('a'):
        # ANCHOR TAGS TEXT
        a_text = ' '.join(list(set([a.text.lower() for a in soup.find_all('a')])))  # anchor tags text combined

        # checking query terms -----------------------------------------
        if all([q in a_text for q in query_terms]):  # all terms in anchor text
            relevance += 0.25
        elif any([q in a_text for q in query_terms]):  # at least one term in anchor text but not all
            relevance += 0.15
        else:
            pass  # keep relevance as is

        # checking synonyms_list terms ----------------------------------
        if all([q in a_text for q in synonyms_list]):  # all terms in anchor text
            relevance += 0.2
        elif any([q in a_text for q in synonyms_list]):  # at least one term in anchor text but not all
            relevance += 0.1
        else:
            pass  # keep relevance as is

        # checking lemmatized words -----------------------------------------
        if all([q in a_text for q in lemmatized_words]):  # all terms in anchor text
            relevance += 0.2
        elif any([q in a_text for q in lemmatized_words]):  # at least one term in anchor text but not all
            relevance += 0.1
        else:
            pass  # keep relevance as is

    if soup.find_all('b'):
        # BOLD TEXT
        bold = ' '.join(list(set([b.text.lower() for b in soup.find_all('b')])))  # bold text combined

        # checking query terms -----------------------------------------
        if all([q in bold for q in query_terms]):  # all terms in bold text
            relevance += 0.25
        elif any([q in bold for q in query_terms]):  # at least one term in bold text but not all
            relevance += 0.15
        else:
            pass  # keep relevance as is

        # checking synonyms_list terms ----------------------------------
        if all([q in bold for q in synonyms_list]):  # all terms in bold text
            relevance += 0.2
        elif any([q in bold for q in synonyms_list]):  # at least one term in bold text but not all
            relevance += 0.1
        else:
            pass  # keep relevance as is

        # checking lemmatized words -----------------------------------------
        if all([q in bold for q in lemmatized_words]):  # all terms in bold text
            relevance += 0.2
        elif any([q in bold for q in lemmatized_words]):  # at least one term in bold text but not all
            relevance += 0.1
        else:
            pass  # keep relevance as is

    # REMAINING PAGE TEXT
    remove_checked = [s.extract() for s in soup(['title', 'b', 'a', 'h1'])]  # remove title, anchors, h1 and bold text
    page_text = soup.text.replace('\n', '').lower()  # page text (after extracting already checked tags)

    # checking query terms -----------------------------------------
    if all([q in page_text for q in query_terms]):  # all terms in remaining text
        relevance += 0.5
    elif any([q in page_text for q in query_terms]):  # at least one term in remaining text but not all
        relevance += 0.4
    else:
        pass  # keep relevance as is

    # checking synonyms_list terms ----------------------------------
    if all([q in page_text for q in synonyms_list]):  # all terms in remaining text
        relevance += 0.45
    elif any([q in page_text for q in synonyms_list]):  # at least one term in remaining text but not all
        relevance += 0.35
    else:
        pass  # keep relevance as is

    # checking lemmatized words -----------------------------------------
    if all([q in page_text for q in lemmatized_words]):  # all terms in remaining text
        relevance += 0.45
    elif any([q in page_text for q in lemmatized_words]):  # at least one term in remaining text but not all
        relevance += 0.35
    else:
        pass  # keep relevance as is

    return relevance


def get_synonyms_and_lemmatized(query):
    """ returns a dict with a list of synonyms per word in the query """

    query = query.lower()

    # remove punctuation from query
    punctuation = set(string.punctuation)
    query = ''.join(x for x in query if x not in punctuation)

    words = word_tokenize(query)

    pos = {}  # part of speech
    for word in words:
        pos.update({word: pos_tag([word], tagset='universal')[0][1]})

    simplified_pos_tags = {}

    for x in pos.keys():
        if pos[x] == 'NOUN':
            simplified_pos_tags.update({x: 'n'})
        elif pos[x] == 'VERB':
            simplified_pos_tags.update({x: 'v'})
        elif pos[x] == 'ADJ':
            simplified_pos_tags.update({x: 'a'})
        elif pos[x] == 'ADV':
            simplified_pos_tags.update({x: 'r'})
        else:
            simplified_pos_tags.update({x: 'n'})  # consider everything else to be a noun

    synonyms = {}
    for w in words:
        synonyms[w] = []

    for w in words:
        if len(wordnet.synsets(w, pos=simplified_pos_tags[w])) != 0:
            s = [x.lower().replace('_', ' ') for x in wordnet.synsets(w, pos=simplified_pos_tags[w])[0].lemma_names() if
                 x.lower() != w]
            for x in s:
                if x not in synonyms[w]:
                    synonyms[w].append(x)

    wordnet_lemmatizer = WordNetLemmatizer()
    # lemmatize all words, return only those which aren't the same as the word
    lemmatized_words = [wordnet_lemmatizer.lemmatize(w, simplified_pos_tags[w]) for w in words if
                        wordnet_lemmatizer.lemmatize(w, simplified_pos_tags[w]) != w]

    return synonyms, list(set(lemmatized_words))


def visit_url(url, page_link_limit):
    """ parses a page to extract text and first k links; returns HTML text and normalized links """

    try:
        res = requests.get(url, proxies=proxies)
        if res.status_code == 200 and 'text/html' in res.headers['Content-Type']:  # also checking MIME type
            html_text = res.text
            soup = BeautifulSoup(res.content, 'lxml')
            f_links = soup.find_all('frame')
            a_links = soup.find_all('a')

            # check if the page has a <base> tag to get the base URL for relative links
            base = soup.find('base')
            if base is not None:
                base_url = base.get('href')
            else:
                # construct the base URL
                scheme = urlparse(url).scheme
                domain = urlparse(url).netloc
                base_url = scheme + '://' + domain

            src = [urljoin(base_url, f.get('src')) for f in f_links]
            href = [urljoin(base_url, a.get('href')) for a in a_links]

            links = list(set(src + href))[:page_link_limit]
            links = [url_normalize(l) for l in links if pre_validate_link(url_normalize(l))]
            # pre_validate before enqueue, but validate after dequeue

            return html_text, links
        else:
            return None, None
    except:
        return None, None


def get_harvest_rate(parsed_urls, threshold):
    """ return harvest rate i.e. # relevant links/# total links parsed """

    total_parsed = len(parsed_urls.get_keys())
    total_relevant = 0

    for link in parsed_urls.get_keys():
        if parsed_urls.get_item(link)[2] >= threshold:
            total_relevant += 1

    harvest_rate = total_relevant/total_parsed

    return harvest_rate


def create_log(parsed_urls, query, num_start_pages, num_crawled, page_link_limit, n, mode, harvest_rate, threshold,
               total_time):
    """ creates a log file for the crawler """

    file = open('crawler_log.txt', 'w')

    file.write('Query: ' + query + '\n')
    file.write('Number of Crawlable Start Pages: ' + str(num_start_pages) + '\n')
    file.write('Number of URLs to be Crawled: ' + str(n) + '\n')
    file.write('Max. Number of Links to be Scraped per Page: ' + str(page_link_limit) + '\n')
    file.write('Crawl Mode: ' + mode + '\n')

    file.write('\n')
    file.write('Number of URLs Crawled: ' + str(num_crawled) + '\n')
    total_size = sum([parsed_urls.get_item(x)[3] for x in parsed_urls.get_keys()])
    file.write('Total Size (Length) of all Pages Crawled: ' + str(total_size) + '\n')
    if total_time < 1:  # convert to seconds
        total_time *= 60
        file.write('Total Time Elapsed: ' + str(total_time) + ' sec\n')
    else:
        file.write('Total Time Elapsed: ' + str(total_time) + ' min\n')

    file.write('Harvest Rate: ' + str(harvest_rate) + ' at Threshold: ' + str(threshold) + '\n')

    unique_errors = list(set(errors))
    file.write('\nErrors: \n')
    file.write('-------\n')
    for e in unique_errors:
        file.write(str(e) + ': ' + str(errors.count(e)) + '\n')
    file.write('\nURLs Crawled:\n')
    file.write('-------------\n\n')

    counter = 0
    for p in parsed_urls.get_keys():
        file.write(str(counter+1) + '. \n')
        file.write('URL:' + p + '\n')
        num_links, page_promise, relevance, page_size, status_code, timestamp = parsed_urls.get_item(p)

        file.write('Number of Links in Page:' + str(num_links) + '\n')
        file.write('Page Size:' + str(page_size) + '\n')
        file.write('Page Promise: ' + str(page_promise) + '\n')
        file.write('Page Relevance: ' + str(relevance) + '\n')
        file.write('Status Code: ' + str(status_code) + '\n')
        file.write('Crawled at:' + str(timestamp) + '\n')
        file.write('\n\n')
        counter += 1


def crawl():
    query, num_start_pages, n, page_link_limit, mode, relevance_threshold = get_input()
    start_time = time.time()
    start_pages = get_start_pages(query, num_start_pages)

    links_to_parse = PriorityQueue()
    parsed_urls = ParsedURLs()

    # get synonyms list and lemmatized words
    synonyms, lemmatized_words = get_synonyms_and_lemmatized(query)
    # creating a combined list of synonyms without duplicates
    synonyms_list = list(set([s for sublist in list(synonyms.values()) for s in sublist]))

    print('Found %d crawlable start pages:\n' % len(start_pages))
    # enqueue the start pages after computing their promises
    for s in start_pages:
        # promise = get_promise(query, s, mode, 0)  # initially, parent_relevance is 0
        promise = 1  # assuming that all the start pages are equally promising
        links_to_parse.enqueue([promise, s])

    # display the queue
    links_to_parse.display_queue()
    print('\n')

    while links_to_parse and page_count.get_page_num() < n:
        crawler = Crawler(links_to_parse, parsed_urls, query, n, page_link_limit, mode, synonyms_list, lemmatized_words)
        crawler.run()

    end_time = time.time()
    total_time = (end_time - start_time)/60  # minutes

    # compute harvest rate
    harvest_rate = get_harvest_rate(parsed_urls, relevance_threshold)

    # create a crawler log file
    create_log(parsed_urls, query, len(start_pages), len(parsed_urls.get_keys()), page_link_limit, n, mode,
               harvest_rate, relevance_threshold, total_time)


if __name__ == "__main__":
    crawl()