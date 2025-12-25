function trim(s){ gsub(/^[[:space:]]+|[[:space:]]+$/, "", s); return s }
function strip_quotes(s){ s=trim(s); gsub(/^'\''|'\''$/, "", s); gsub(/^"|"$/, "", s); return s }

function parse_alias(line,   l,name,cmd) {
	l=line
	sub(/[[:space:]]*#[[:space:]]*.*/, "", l)
	sub(/^[[:space:]]*alias[[:space:]]+/, "", l)
	name=l; sub(/=.*/, "", name); name=trim(name)
	cmd=l; sub(/^[^=]*=/, "", cmd); cmd=strip_quotes(cmd)
	if (name != "" && cmd != "") amap[name]=cmd
}

function resolve_first(cmd,   full,depth,arr,first,rest) {
	full=cmd
	for (depth=0; depth<10; depth++) {
		split(full, arr, /[[:space:]]+/)
		first=arr[1]

		rest=full
		sub("^[^[:space:]]+[[:space:]]*", "", rest)

		if (first in amap) {
			full = (rest != "") ? (amap[first] " " rest) : amap[first]
		} else break
	}
	return full
}

BEGIN {
	mode = (mode == "" ? "list" : mode)
	ql = tolower(q)

	printf "%-16s | %-30s | %-55s | %s\n", "alias", "command", "full command", "comment"
	printf "%-16s-+-%-30s-+-%-55s-+-%s\n", "----------------", "------------------------------", "-------------------------------------------------------", "------------------------------"
}

FNR==NR {
	if ($0 ~ /^[[:space:]]*alias[[:space:]]+/) parse_alias($0)
	next
}

$0 ~ /^[[:space:]]*alias[[:space:]]+/ {
	orig=$0
	line=$0

	comment=""
	if (match(line, /[[:space:]]*#[[:space:]]*(.*)$/, m)) { comment=m[1]; sub(/[[:space:]]*#[[:space:]]*.*/, "", line) }

	sub(/^[[:space:]]*alias[[:space:]]+/, "", line)
	name=line; sub(/=.*/, "", name); name=trim(name)
	cmd=line; sub(/^[^=]*=/, "", cmd); cmd=strip_quotes(cmd)
	full=resolve_first(cmd)

	if (mode == "search") {
		hay = tolower(name "\n" cmd "\n" full "\n" comment "\n" orig)
		if (index(hay, ql) == 0) next
	}

	printf "%-16s | %-30s | %-55s | %s\n", name, cmd, full, comment
}
