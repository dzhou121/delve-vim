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

function! delve#halt()
    call _delve("halt")
endfunction

function! delve#step()
    call _delve("step")
endfunction

function! delve#next()
    call _delve("next")
endfunction

function! delve#open_all_fold()
    call _delve("open_all_fold")
endfunction

function! delve#close_all_fold()
    call _delve("close_all_fold")
endfunction

function! delve#display_vars()
    call _delve("display_vars")
endfunction

function! delve#restart()
    call _delve("restart")
endfunction

nmap <silent> <C-c> :call delve#new_breakpoint()<cr>
nmap <leader>b :call delve#openwindow()<cr>

sign define delve_breakpoint text=➤ texthl=identifier
sign define delve_breakpoint_confirmed text=➤ texthl=statement
sign define delve_start text=
sign define delve_halt text=
sign define delve_stop text=
sign define delve_next text=
sign define delve_vars linehl=DelveVariables texthl=DelveVariables
hi DelveVariables guibg=#1c1c1c
let g:delve_local_dir = "/Users/Lulu/go/src/"
" let g:delve_remote_dir = "/Users/Lulu/go/src/"
let g:delve_remote_dir = "/root/go/src/"
