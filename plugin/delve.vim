function! Delve()
    call _delve()
endfunction

nmap <silent> <C-c> :call Delve()<cr>

sign define delve_breakpoint text=➤ texthl=statement
