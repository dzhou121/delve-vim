function! s:is_initialized() abort "{{{
  return exists('g:delve#channel_id')
endfunction"}}}

function! delve#init() abort "{{{
  if s:is_initialized()
    return
  endif
  if !exists('g:loaded_remote_plugins')
    runtime! plugin/rplugin.vim
  endif
  call _delve()
endfunction"}}}

function! delve#new_breakpoint()
    call rpcnotify(g:delve#channel_id, 'new_breakpoint')
endfunction

function! delve#openwindow()
    " call _delve("open_window")
    call rpcnotify(g:delve#channel_id, 'open_window')
endfunction

function! delve#start()
    call _delve("start")
endfunction

function! delve#continue()
    call rpcnotify(g:delve#channel_id, 'continue_exec')
endfunction

function! delve#openfold()
    call rpcnotify(g:delve#channel_id, 'openfold')
endfunction

function! delve#halt()
    call rpcnotify(g:delve#channel_id, 'halt')
endfunction

function! delve#step()
    call rpcnotify(g:delve#channel_id, 'step')
endfunction

function! delve#next()
    call rpcnotify(g:delve#channel_id, 'next')
endfunction

function! delve#open_all_fold()
    call rpcnotify(g:delve#channel_id, 'open_all_fold')
endfunction

function! delve#close_all_fold()
    call rpcnotify(g:delve#channel_id, 'close_all_fold')
endfunction

function! delve#display_vars()
    call rpcnotify(g:delve#channel_id, 'display_vars')
endfunction

function! delve#restart()
    call rpcnotify(g:delve#channel_id, 'restart')
endfunction

nmap <silent> <C-c> :call delve#new_breakpoint()<cr>
nmap <leader>b :call delve#openwindow()<cr>

sign define delve_breakpoint text=➤ texthl=identifier
sign define delve_breakpoint_confirmed text=➤ texthl=String
sign define delve_start text=
sign define delve_halt text=
sign define delve_stop text=
sign define delve_next text=
sign define delve_restart text=
sign define delve_vars text=  linehl=DelveVariables texthl=DelveVariables
hi DelveVariables guibg=#1c1c1c
let g:delve_local_dir = "/Users/Lulu/go/src/"
" let g:delve_remote_dir = "/Users/Lulu/go/src/"
let g:delve_remote_dir = "/root/go/src/"

let g:delve_local_sys = "/usr/local/Cellar/go/1.6.2/libexec/src/"
let g:delve_remote_sys = "/usr/local/go/src/"

call delve#init()
