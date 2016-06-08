function! delve#new_breakpoint()
    call _delve()
endfunction

function! delve#openwindow()
    call _delve("open_window")
endfunction

function! delve#start()
    call _delve("start")
endfunction

function! delve#continue()
    call _delve("continue_exec")
endfunction

function! delve#openfold()
    call _delve("openfold")
endfunction

function! delve#restart()
    call _delve("restart")
endfunction

nmap <silent> <C-c> :call delve#new_breakpoint()<cr>
nmap <leader>b :call delve#openwindow()<cr>

sign define delve_breakpoint text=➤ texthl=identifier
sign define delve_breakpoint_confirmed text=➤ texthl=statement
let g:delve_local_dir = "/Users/Lulu/go/src/"
let g:delve_remote_dir = "/root/go/src/"
