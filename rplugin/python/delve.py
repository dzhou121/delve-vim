# -*- coding: utf-8 -*-
import neovim
import socket
import json


@neovim.plugin
class Main(object):
    def __init__(self, vim):
        self.vim = vim
        self.prefix = ' '.decode('utf8')
        self.close_prefix = ' '.decode('utf8')
        self.indent = ' ' * 2

    def recv_timeout(self, timeout=2):
        total_data = []
        while 1:
            data = self.s.recv(8192)
            if data == '\n':
                break
            elif data:
                total_data.append(data)
                if data.endswith('\n'):
                    break
            else:
                break

        return ''.join(total_data)

    def send(self, msg):
        self.s.send(json.dumps(msg))
        reply = self.recv_timeout()
        return reply

    def list_vars(self, goroutineid):
        msg = {
            "method": "RPCServer.ListLocalVars",
            "params": [{
                "Scope": {
                    "GoroutineID": goroutineid,
                },
                "Cfg": {
                    "FollowPointers": True,
                    "MaxVariableRecurse": 3,
                    "MaxStringLen": 100,
                    "MaxArrayValues": 100,
                    "MaxStructFields": 100,
                },
            }],
        }
        return self.send(msg)

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
        return self.send(msg)

    def delv_command(self, cmd):
        msg = {
            "method": "RPCServer.Command",
            "params": [{
                "name": cmd,
            }],
        }
        return self.send(msg)

    def get_all_signs(self, output):
        signs = []
        lines = output.split("\n")
        for line in lines:
            if "name=delve_breakpoint" in line:
                signs.append(line.split("line=")[1].split(" ")[0])

        return signs

    def start(self):
        pass

    def dump_children(self, buf, child, space):
        for sub_child in child:
            name = sub_child['name']
            value = sub_child['value']
            var_type = sub_child['type']
            if var_type == "string":
                value = '"%s"' % value

            if value:
                var_type = ""
            else:
                var_type = '<%s>' % var_type

            if name or value:
                if (var_type.startswith("<*uint") or
                        var_type.startswith("<*int")):
                    if len(sub_child['children']) == 0:
                        value = "nil "

                elif (var_type.startswith("<*") and
                        (not (len(sub_child['children']) > 0 and
                        len(sub_child['children'][0]['children']) > 0))):
                    value = "nil "
                buf.append("%s%s: %s%s" % (
                    space * " ",
                    name,
                    value,
                    var_type,
                ))

                new_space = space + 4
            else:
                new_space = space
            self.dump_children(buf, sub_child['children'], new_space)

    def halt(self):
        pass

    def continue_exec(self):
        self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.s.connect(("185.40.140.123", 2345))
        r = self.delv_command("continue")
        result = json.loads(r)
        if result.get('error'):
            return

        bp_info = result['result']['State']
        current_thread = bp_info['currentThread']
        # print current_thread['goroutineID']
        r = self.list_vars(current_thread['goroutineID'])
        r = json.loads(r)
        # print r
        # local_vars = bp_info['locals']
        for buf in self.vim.buffers:
            if buf.name.endswith("__Delve_Vars__"):
                buf[:] = []
                self.local_vars = {}
                self.format_parent(self.local_vars, r['result']['Variables'])
                self.set_local_vars(buf)

    def format_var_line(self, var):
        name = var['name']
        value = var['value']
        var_type = var['type']
        if value:
            var_type = ""
        else:
            var_type = '<%s>' % var_type
        if var_type.startswith('<*') and not var['children']:
            value = "nil "

        prefix = len(self.prefix) * ' '
        if var['children']:
            prefix = self.prefix
        return("%s%s: %s%s" % (prefix, name, value, var_type))

    def set_local_vars(self, buf):
        for name, var in self.local_vars.items():
            buf.append(self.format_var_line(var))

    def format_parent(self, parent, children):
        for child in children:
            name = child['name']
            value = child['value']
            var_type = child['type']
            if name:
                parent[name] = {}
                parent[name]['name'] = name
                parent[name]['value'] = value
                parent[name]['type'] = var_type
                parent[name]['children'] = {}
                self.format_parent(parent[name]['children'], child['children'])
            else:
                if value:
                    name = "noname"
                    parent[name] = {}
                    parent[name]['name'] = name
                    parent[name]['value'] = value
                    parent[name]['type'] = var_type
                    parent[name]['children'] = {}
                    self.format_parent(parent[name]['children'],
                                       child['children'])
                else:
                    self.format_parent(parent, child['children'])

    def restart(self):
        self.delv_command("restart")

    def get_key(self, line, indent_num):
        parts = line.split(self.indent)
        return parts[indent_num][2:].split(':')[0]

    def find_parent_key(self, keys, buf, indent_num, n):
        line = buf[n].decode('utf8')
        key = self.get_key(line, indent_num)
        keys.insert(0, key)
        if indent_num == 0:
            return

        parent_prefix = (indent_num - 1) * self.indent + self.close_prefix
        while 1:
            n = n - 1
            line = buf[n].decode('utf8')
            if line.startswith(parent_prefix):
                self.find_parent_key(keys, buf, indent_num - 1, n)
                return

    def openfold(self):
        exits = False
        for win in self.vim.windows:
            if win.buffer.name.endswith("__Delve_Vars__"):
                buf = win.buffer
                n = win.cursor[0] - 1
                exits = True
                break

        if not exits:
            return

        line = buf[n].decode('utf8')
        indent_num = 0
        parts = line.split(self.indent)
        for p in parts:
            if p == '':
                indent_num += 1
            else:
                if p.startswith(self.prefix):
                    self._openfold(buf, indent_num, n)
                    return
                elif p.startswith(self.close_prefix):
                    self._closefold(buf, indent_num, n)
                    return

    def _closefold(self, buf, indent_num, n):
        for i, line in enumerate(buf):
            if i < n + 1:
                continue
            line = line.decode('utf8')
            j = len(self.indent * indent_num) + len(self.prefix)
            c = line[j:j + 2]
            if c != '  ' and c != self.prefix and c != self.close_prefix:
                break

        del buf[n+1:i]
        buf[n] = buf[n].decode('utf8').replace(
            self.close_prefix, self.prefix).encode('utf8')

    def _openfold(self, buf, indent_num, n):
        keys = []
        self.find_parent_key(keys, buf, indent_num, n)
        # print keys

        children = self.local_vars
        for k in keys:
            children = children[k]['children']
        for i, child in children.items():
            buf.append(self.indent * (indent_num + 1) + self.format_var_line(child), n + 1)
        buf[n] = buf[n].decode('utf8').replace(self.prefix, self.close_prefix).encode('utf8')

    def open_window(self):
        self.vim.command_output("keepalt vertical botright split __Delve_Vars__")
        self.vim.command_output("setlocal filetype=delve")
        self.vim.command_output("setlocal buftype=nofile")
        self.vim.command_output("setlocal bufhidden=hide")
        self.vim.command_output("setlocal noswapfile")
        self.vim.command_output("setlocal nobuflisted")
        # self.vim.command_output("setlocal nomodifiable")
        self.vim.command_output("setlocal nolist")
        self.vim.command_output("setlocal nowrap")

        maps = [
            ['s',             'delve#start()'],
            ['c',             'delve#continue()'],
            ['r',             'delve#restart()'],
            ['o',             'delve#openfold()'],
        ]

        for keymap in maps:
            cmd = 'nnoremap <silent> <buffer> %s :call %s<CR>' % (
                keymap[0], keymap[1]
            )

            self.vim.command_output(cmd)

#         self.vim.command_output("keepalt split __Delve_log__")
#         self.vim.command_output("setlocal filetype=delve")
#         self.vim.command_output("setlocal buftype=nofile")
#         self.vim.command_output("setlocal bufhidden=hide")
#         self.vim.command_output("setlocal noswapfile")
#         self.vim.command_output("setlocal nobuflisted")
#         self.vim.command_output("setlocal nomodifiable")
#         self.vim.command_output("setlocal nolist")
#         self.vim.command_output("setlocal nowrap")

        for buf in self.vim.buffers:
            if buf.name.endswith("__Delve_Vars__"):
                """

        



                """
                buf.append("➤")

    @neovim.function("_delve")
    def testcommand(self, args):
        try:
            self.run(args)
        except:
            pass

    def run(self, args):
        if len(args) > 0:
            c = getattr(self, args[0])
            c()
            return
            if args[0] == 'open_window':
                self.open_window()
                return

        path = self.vim.command_output("silent echo expand('%:p')")[1:]
        row = self.vim.current.window.cursor[0]

        if not path:
            return

        local_dir = self.vim.eval("g:delve_local_dir")
        if local_dir not in path:
            return

        remote_dir = self.vim.eval("g:delve_remote_dir")
        remote_path = path.replace(local_dir, remote_dir)

        signs = self.vim.command_output("silent sign place file=%s" % path)
        if str(row) in signs:
            self.vim.command("sign unplace %s file=%s" % (row, path))
        else:
            cmd = "sign place %s line=%s name=delve_breakpoint file=%s" % (
                row, row, path
            )
            self.vim.command(cmd)
            self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.s.connect(("185.40.140.123", 2345))
            reply = self.create_breakpoint(remote_path, row)
            reply = json.loads(reply)
            if not reply.get('error'):
                cmd = ("sign place %s line=%s "
                       "name=delve_breakpoint_confirmed file=%s" % (
                           row, row, path
                       ))
                self.vim.command(cmd)


if __name__ == "__main__":
    vim = neovim.attach("socket", path='/tmp/nvim')
    m = Main(vim)
    m.continue_exec()
    # for buffer in vim.buffers:
    #     print buffer.name
