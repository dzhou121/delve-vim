syntax match DelveValue ': \zs\S*\ze\n'
syntax match DelveValue ': \zs.*\ze <'
syntax match DelveType '<.*>'
syntax match DelveNil 'nil'
syntax match DelveString '".*"'
syntax match DelveStart ''
syntax match DelveHalt ''
syntax match DelveStop ''
syntax match DelveNext ''
syntax match DelveRestart ''

hi link DelveType Type
hi link DelveString String
hi link DelveValue Identifier
hi link DelveNil Error
hi link DelveStart String
hi link DelveHalt String
hi link DelveStop ErrorMsg
hi link DelveNext Comment
hi link DelveRestart Comment
