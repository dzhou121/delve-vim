import neovim
import socket
import json
import time


def restart():
    msg = {
        "method": "RPCServer.Restart",
        "params": [{}],
    }
    send(msg)


def command(cmd):
    msg = {
        "method": "RPCServer.Command",
        "params": [{
            "name": cmd,
        }],
    }
    send(msg)


def list_vars():
    msg = {
        "method": "RPCServer.ListLocalVars",
        "params": [{
            "Scope": {"GoroutineID": 4532},
        }],
    }
    send(msg)


def list_goroutines():
    msg = {
        "method": "RPCServer.ListGoroutines",
        "params": [{
        }],
    }
    send(msg)


def get_data():
    while 1:
        print "now getting data"
        # data = s.recv(10000)
        # print data


@neovim.plugin
class Main(object):
    def __init__(self, vim):
        self.vim = vim

    def send(self, msg):
        self.s.send(json.dumps(msg))
        print self.s.recv(9000)

    def create_breakpoint(self, fname, line):
        msg = {
            "method": "RPCServer.CreateBreakpoint",
            "params": [{
                "Breakpoint": {
                    "file": "",
                    "line": 72,
                }
            }]
        }
        msg["params"][0]["Breakpoint"]["file"] = fname
        msg["params"][0]["Breakpoint"]["line"] = line
        self.send(msg)

    def get_all_signs(self, output):
        signs = []
        lines = output.split("\n")
        for line in lines:
            if "name=delve_breakpoint" in line:
                signs.append(line.split("line=")[1].split(" ")[0])

        return signs

    @neovim.function("_delve")
    def testcommand(self, args):
        self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.s.connect(("185.40.140.123", 2345))
        path = self.vim.command_output("silent echo expand('%:p')")[1:]
        row = self.vim.current.window.cursor[0]

        if not path:
            return

        signs = self.vim.command_output("silent sign place file=%s" % path)
        if str(row) in signs:
            self.vim.command("sign unplace %s file=%s" % (row, path))
        else:
            self.create_breakpoint(path, row)
            cmd = "sign place %s line=%s name=delve_breakpoint file=%s" % (
                row, row, path
            )
            self.vim.command(cmd)


if __name__ == "__main__":
    vim = neovim.attach("socket", path='/tmp/nvim')
    m = Main(vim)
    m.testcommand("slkd")
