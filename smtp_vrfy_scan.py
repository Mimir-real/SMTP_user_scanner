import asyncio
import string
import argparse
import sys

parser = argparse.ArgumentParser()
parser.add_argument('target')
parser.add_argument('wordlist')
parser.add_argument('--pipelining', action='store_true')
parser.add_argument('--delay', default=0.2)
parser.add_argument('--verbose', action='store_true',
                    help='Print each send and receive action')
parser.add_argument('--script-mode', action='store_true',
                    help='Print only result') # TODO
args = parser.parse_args()


existing = set()
nonexisting = set()
wordlist_len: int

USERNAME_ALLOWED_CHARSET = set(string.ascii_letters + string.digits + '_@-$')


def is_username_valid(username: str) -> bool:
    return all((c in USERNAME_ALLOWED_CHARSET) for c in username)


def get_wordlist(filename: str) -> set:
    """
    Reads file and checks against the allowed unix user charset
    :param filename: name of wordlist file
    :return set of words
    """
    with open(filename, 'r') as f:
        wordlist = set(w.strip() for w in f.readlines())
        for word in wordlist:
            if not is_username_valid(word):
                raise Exception('Bad character in username')
        return wordlist


def debug_print(*arg):
    if args.verbose:
        print(*arg, file=sys.stderr)


async def send_commands(writer: asyncio.StreamWriter, wordlist):
    for username in wordlist:
        command = b'VRFY ' + username.encode()
        debug_print(command)
        writer.write(command + b'\n')
        await writer.drain()
        await asyncio.sleep(args.delay)


async def receive_and_report(reader: asyncio.StreamReader):
    # while not (received_line := (await reader.readuntil()).decode()).startswith('421'):
    while not reader.at_eof():
        received_line = (await reader.readline()).decode()
        debug_print(received_line)

        if received_line.startswith('2'):
            if received_line.startswith('252'):
                username = received_line.split()[2]
                existing.add(username)
        elif received_line.startswith('550'):
            username = received_line.split()[2][1:-2]
            nonexisting.add(username)
        else:
            debug_print('Error:', received_line)
            break

        if len(existing) + len(nonexisting) == wordlist_len:
            break
        await asyncio.sleep(args.delay)


def parse_target(target: str) -> tuple:
    match target.count(':'):
        case 0:
            host = target
            port = 25
        case 1:
            host, port = target.split(':')
        case _:
            raise ValueError('Invalid target format')
    return host, port


def report_progress():
    print('Found:', existing)
    print('Tried but not found:', nonexisting)
    progress = len(existing) + len(nonexisting)
    print('Progress: {}/{} ({:.2%})'.format(
        progress, wordlist_len, progress / wordlist_len
    ))


async def main():
    global wordlist_len
    print('Loading wordlist...')
    to_check = get_wordlist(args.wordlist)
    wordlist_len = len(to_check)
    print('Wordlist loaded')

    host, port = parse_target(args.target)

    print('Starting scan')
    while (to_check := to_check - existing - nonexisting):
        reader, writer = await asyncio.open_connection(host, port)

        await asyncio.gather(send_commands(writer, to_check),
                             receive_and_report(reader))
        writer.close()
        await writer.wait_closed()
        report_progress()


if __name__ == '__main__':
    asyncio.run(main())
