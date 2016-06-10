# -*- coding: utf-8 -*-
import os
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
        self.local_vars = {}
        self.break_points = {}
        # self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # self.s.connect(("185.40.140.123", 2345))
        self.delve_buf = None
        self.delve_buf_name = '__Delve_Vars__'
        # self.s.connect(("185.40.140.123", 2345))

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
                    "MaxVariableRecurse": 5,
                    "MaxStringLen": 100,
                    "MaxArrayValues": 100,
                    "MaxStructFields": 100,
                },
            }],
        }
        return self.send(msg)

    def delete_breakpoint(self, bp_id):
        msg = {
            "method": "RPCServer.ClearBreakpoint",
            "params": [{
                "Id": bp_id,
            }]
        }
        return self.send(msg)

    def create_breakpoint(self, fname, line):
        msg = {
            "method": "RPCServer.CreateBreakpoint",
            "params": [{
                "Breakpoint": {
                    "file": fname,
                    "line": line,
                    "goroutine": False,
                    "stacktrace": 0,
                    # "LoadLocals": {
                    #     "FollowPointers": True,
                    #     "MaxVariableRecurse": 0,
                    #     "MaxStringLen": 100,
                    #     "MaxArrayValues": 100,
                    #     "MaxStructFields": 100,
                    # },
                }
            }]
        }
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

    def next(self):
        f = os.path.join(os.getcwd(), "__Delve_Vars__")
        self.vim.command("sign place 1 line=1 name=delve_next file=" + f)
        r = self.delv_command("next")
        result = json.loads(r)
        if result.get('error'):
            return
        self.display_result(result)
        self.vim.command("sign unplace 1 file=%s" % f)

    def halt(self):
        r = self.delv_command("halt")
        for buf in self.vim.buffers:
            if buf.name.endswith("__Delve_Vars__"):
                buf.append(json.dumps(json.loads(r)))

    def step(self):
        r = self.delv_command("step")

        result = json.loads(r)
        if result.get('error'):
            return

        self.display_result(result)

    def continue_exec(self):
        f = os.path.join(os.getcwd(), "__Delve_Vars__")
        self.vim.command("sign place 1 line=1 name=delve_start file=" + f)

        r = self.delv_command("continue")
        result = json.loads(r)
        # for buf in self.vim.buffers:
        #     if buf.name.endswith("__Delve_Vars__"):
        #         buf.append(json.dumps(json.loads(r)))
        #         return
        if result.get('error'):
            return

        self.display_result(result, var=True)

        self.vim.command("sign unplace 1 file=%s" % f)

    def jump_to(self, delve_win, f, c_line):
        exists = False
        for win in self.vim.windows:
            buf_name = os.path.join(os.getcwd(), win.buffer.name)
            if buf_name == f:
                self.vim.current.window = win
                self.vim.current.window.cursor = (c_line, 1)
                self.vim.current.window = delve_win
                exists = True
                break

        if not exists:
            for win in self.vim.current.tabpage.windows:
                if not win.buffer.name.endswith("__Delve_Vars__") and \
                        "NERD_tree" not in win.buffer.name:
                    exists = True
                    self.vim.current.window = win
                    self.vim.command_output("e %s" % f)
                    self.vim.current.window.cursor = (c_line, 1)

            if not exists:
                self.vim.command_output("vertical split")
                self.vim.command_output("e %s" % f)
                self.vim.current.window.cursor = (c_line, 1)

    def display_result(self, result, var=False):
        bp_info = result['result']['State']
        current_thread = bp_info['currentThread']
        self.current_goroutine = current_thread["goroutineID"]
        c_line = int(current_thread['line'])
        c_file = current_thread['file']

        for buf in self.vim.buffers:
            if buf.name.endswith("__Delve_Vars__"):
                break

        local_dir = self.vim.eval("g:delve_local_dir")
        remote_dir = self.vim.eval("g:delve_remote_dir")
        f = c_file.replace(remote_dir, local_dir)
        for win in self.vim.windows:
            if win.buffer.name.endswith("__Delve_Vars__"):
                delve_win = win

        self.jump_to(delve_win, f, c_line)

        if var:
            self.display_vars()

        # r = self.list_vars(self.current_goroutine)
        # r = json.loads(r)
        # source_local_vars = r['result']['Variables']

        # for buf in self.vim.buffers:
        #     if buf.name.endswith("__Delve_Vars__"):
        #         local_vars = {}
        #         self.format_parent({}, local_vars, self.local_vars,
        #                            source_local_vars)
        #         self.local_vars = local_vars
        #         self.set_local_vars(buf)

    def display_vars(self):
        f = os.path.join(os.getcwd(), "__Delve_Vars__")
        self.vim.command("sign place 1 line=1 name=delve_vars file=" + f)

        r = self.list_vars(self.current_goroutine)
        r = json.loads(r)
        source_local_vars = r['result']['Variables']

        for buf in self.vim.buffers:
            if buf.name.endswith("__Delve_Vars__"):
                local_vars = {}
                self.format_parent({}, local_vars, self.local_vars,
                                   source_local_vars)
                self.local_vars = local_vars
                self.set_local_vars(buf)

        self.vim.command("sign unplace 1 file=%s" % f)

    def format_var_line(self, var):
        name = var['name']
        # if ' ' in name:
        #     name = name.split(' ')[-1]
        value = var['value']
        var_type = var['type']

        var_type = '<%s>' % var_type
        if value:
            if var_type == "<string>":
                value = value.replace("\n", "\\n")
                value = '"%s"' % value
                var_type = ""
            elif var_type in ["<bool>", "<uint>", "<uint32>",
                              "<int>", "<int64>", "int32"]:
                var_type = ""
            else:
                value = value + ' '

        if var_type.startswith('<*') and not var['children']:
            value = "nil "

        prefix = len(self.prefix) * ' '
        if var['children']:
            if var.get('expanded'):
                prefix = self.close_prefix
            else:
                prefix = self.prefix
        return("%s%s: %s%s" % (prefix, name, value, var_type))

    def set_local_vars(self, buf, expand_all=None):
        local_vars = [var for name, var in self.local_vars.items()]
        local_vars.sort(key=lambda d: len(d['children']) == 0)
        lines = []
        indent_num = 0
        for var in local_vars:
            if expand_all is not None:
                var['expanded'] = expand_all
            lines.append((self.indent * indent_num +
                          self.format_var_line(var)).encode('utf8'))
            self._openfold_lines(lines, indent_num, var, expand_all=expand_all)

        buf[:] = lines

    def format_parent(self, parent, children, original_children,
                      source_children):
        for i, child in enumerate(source_children):
            name = child['name']
            if parent.get('type', '').startswith('map['):
                if i % 2 == 0:
                    name = str(i / 2) + ' key'
                else:
                    name = str(i / 2) + ' value'
            elif parent.get('type', '').startswith('[]'):
                name = str(i)

            value = child['value']
            var_type = child['type']
            if name:
                children[name] = {}
                children[name]['name'] = name
                children[name]['value'] = value
                children[name]['type'] = var_type
                children[name]['children'] = {}
                children[name]['expanded'] = original_children.get(
                    name, {}).get('expanded', False)
                self.format_parent(
                    children[name],
                    children[name]['children'],
                    original_children.get(name, {}).get('children', {}),
                    child['children'])
            else:
                if value:
                    name = "noname"
                    children[name] = {}
                    children[name]['name'] = name
                    children[name]['value'] = value
                    children[name]['type'] = var_type
                    children[name]['children'] = {}
                    self.format_parent(
                        children[name],
                        children[name]['children'],
                        original_children.get(
                            name, {}).get('children', {}),
                        child['children'])
                else:
                    self.format_parent(parent,
                                       children,
                                       original_children,
                                       child['children'])

    def restart(self):
        msg = {
            "method": "RPCServer.Restart",
            "params": [{
            }],
        }
        for buf in self.vim.buffers:
            if buf.name.endswith("__Delve_Vars__"):
                buf.append("start sending")
        reply = self.send(msg)
        for buf in self.vim.buffers:
            if buf.name.endswith("__Delve_Vars__"):
                buf.append(json.dumps(json.loads(reply)))

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

    def open_all_fold(self):
        for buf in self.vim.buffers:
            if buf.name.endswith("__Delve_Vars__"):
                self.set_local_vars(buf, expand_all=True)

    def close_all_fold(self):
        for buf in self.vim.buffers:
            if buf.name.endswith("__Delve_Vars__"):
                self.set_local_vars(buf, expand_all=False)

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
        parent = self.find_parent(buf, indent_num, n)
        parent['expanded'] = False
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

    def find_parent(self, buf, indent_num, n):
        keys = []
        self.find_parent_key(keys, buf, indent_num, n)

        children = self.local_vars
        for k in keys:
            parent = children[k]
            children = parent['children']

        return parent

    def _openfold_lines(self, lines, indent_num, parent, expand_all=None):
        children = parent['children']
        children = [child for i, child in children.items()]

        if parent.get('type', '').startswith('map['):
            children.sort(key=lambda d: d['name'])
        else:
            children.sort(key=lambda d: len(d['children']) == 0)
        indent_num += 1
        if expand_all is False:
            for child in children:
                child['expanded'] = expand_all
                self._openfold_lines(lines, indent_num, child,
                                     expand_all=expand_all)
        if parent.get('expanded', False):
            for child in children:
                if expand_all is not None:
                    child['expanded'] = expand_all
                lines.append((self.indent * indent_num +
                             self.format_var_line(child)).encode('utf8'))
                self._openfold_lines(lines, indent_num, child,
                                     expand_all=expand_all)

    def _openfold(self, buf, indent_num, n):
        parent = self.find_parent(buf, indent_num, n)
        parent['expanded'] = True
        buf[n] = buf[n].decode('utf8').replace(
            self.prefix, self.close_prefix).encode('utf8')

        lines = []
        self._openfold_lines(lines, indent_num, parent)
        buf.append(lines, n + 1)

        # m = n
        # indent_num += 1
        # for child in children:
        #     m += 1
        #     buf.append(self.indent * indent_num +
        #                self.format_var_line(child),
        #                m)
        #     if child.get('expanded', False):
        #         m += self._openfold(buf, indent_num, m)
        # return m - n

    def find_delve_win(self):
        for w in self.vim.current.tabpage.windows:
            if self.delve_buf_name in w.buffer.name:
                return w

    def find_delve_buf(self):
        for buf in self.vim.buffers:
            if self.delve_buf_name in buf.name:
                self.delve_buf = buf
                return buf

    def init_delve_buf(self):
        self.find_delve_buf()

        self.vim.command_output("setlocal filetype=delve")
        self.vim.command_output("setlocal buftype=nofile")
        self.vim.command_output("setlocal bufhidden=hide")
        self.vim.command_output("setlocal noswapfile")
        self.vim.command_output("setlocal nobuflisted")
        self.vim.command_output("setlocal nomodifiable")
        self.vim.command_output("setlocal nolist")
        self.vim.command_output("setlocal nowrap")

        self.vim.command("nmap cgc c")
        self.vim.command("nunmap cgc")
        self.vim.command("nmap dd d")
        self.vim.command("nunmap dd")

        maps = [
            ['s',             'delve#start()'],
            ['c',             'delve#continue()'],
            ['r',             'delve#restart()'],
            ['a',             'delve#halt()'],
            ['m',             'delve#next()'],
            ['o',             'delve#openfold()'],
            ['O',             'delve#open_all_fold()'],
            ['X',             'delve#close_all_fold()'],
            ['d',             'delve#display_vars()'],
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

    def open_window(self):
        delve_win = self.find_delve_win()
        if delve_win:
            old_win = self.vim.current.window
            old_is_self = self.delve_buf_name in old_win.buffer.name
            self.vim.current.window = delve_win
            self.vim.command("close")
            if not old_is_self:
                self.vim.current.window = old_win
            return

        # check if the buf exists or not
        delve_buf_exits = self.delve_buf is not None

        # at this step, it means the win is not open, so open it first
        self.vim.command_output(
            "keepalt vertical botright split %s" % self.delve_buf_name)
        delve_win = self.find_delve_win()

        if not delve_buf_exits:
            self.init_delve_buf()
            lines = [
                '                 ',
                '                      ',
                '> Variables           ',
            ]

            self.vim.command("setlocal modifiable")
            self.delve_buf[:] = lines
            self.vim.command("setlocal nomodifiable")
        # indent = (delve_win.width - len(line)) / 2
        # if indent < 0:
        #     indent = 0
        # if len(self.delve_buf) == 0:
        #     self.delve_buf[:] = [line]
        # else:
        # self.delve_buf[0] = ' ' * indent + line + ' ' * indent

        # for buf in self.vim.buffers:
        #     if buf.name.endswith("__Delve_Vars__"):
        #         """
# 
#         
# 
# 
# 
        #         """
                # f = os.path.join(os.getcwd(), "__Delve_Vars__")
                # self.vim.command("sign place 1 line=1 name=delve_start file=" + f)
                # self.vim.command("sign place 2 line=2 name=delve_stop file=" + f)

    @neovim.function("_delve")
    def testcommand(self, args):
        try:
            self.run(args)
        except Exception as e:
            for buf in self.vim.buffers:
                if buf.name.endswith("__Delve_Vars__"):
                    buf.append(str(e))

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
        bp_key = "%s:%s" % (path, row)
        if str(row) in signs:
            bp_id = self.break_points.get(bp_key)
            if bp_id:
                reply = self.delete_breakpoint(bp_id)
                reply = json.loads(reply)
                error = reply.get('error', '')
                if error:
                    self.vim.command('echo "%s"' % error)

                self.vim.command("sign unplace %s file=%s" % (row, path))
        else:
            cmd = "sign place %s line=%s name=delve_breakpoint file=%s" % (
                row, row, path
            )
            self.vim.command(cmd)
            reply = self.create_breakpoint(remote_path, row)
            reply = json.loads(reply)
            error = reply.get('error', '')
            if not error:
                bp_id = reply['result']['Breakpoint']['id']
                self.break_points[bp_key] = bp_id
            if not error or error.startswith("Breakpoint exists"):
                cmd = ("sign place %s line=%s "
                       "name=delve_breakpoint_confirmed file=%s" % (
                           row, row, path
                       ))
                self.vim.command(cmd)
            else:
                self.vim.command("sign unplace %s file=%s" % (row, path))
                self.vim.command('echo "%s"' % error)


if __name__ == "__main__":
    vim = neovim.attach("socket", path='/tmp/nvim')
    m = Main(vim)
    m.continue_exec()
    # for buffer in vim.buffers:
    #     print buffer.name
