"""PreToolUse guard (wired in the local .claude/settings.json): refuses, before it runs, a tool call that breaks a
project rule no later check could undo. Exit 2 = refused (the reason is shown to the session); exit 0 = allowed.
A guard bug never blocks work: any exception allows the call and says so (exit 1, shown, not blocking).

Rules held here:
- the secrets file `.env` is never read or shown (CONTEXT, top warning); `.env.example` is fine;
- git: hooks are never skipped, no force push, no `reset --hard`.
Test: python scripts/guard.py --selftest   (pytest runs it too)
"""
import json, re, sys

# `.env`, `.env.local`... as a whole token (not `foo.env`, not `.environment`)
ENV = re.compile(r'(?<![\w.-])\.env(\.[\w.-]+)?(?![\w-])')
READ = re.compile(r'(?i)\b(cat|type|get-content|gc|less|more|head|tail|grep|rg|sed|awk|nl|tac|strings|xxd|od|base64|cp|copy|copy-item|python3?|node)\b|(^|[;&|]\s*)(source|\.)\s')
WHY_ENV = 'the .env secrets file is never read or shown (CONTEXT): ask the author for the value instead'
RULES = [
    (r'--no-verify\b', 'hooks are never skipped (the pre-push hook runs the project check)'),
    (r'\bgit\s+push\b[^\n]*(--force\b|\s-f\b)', 'no force push'),
    (r'\bgit\s+reset\s+--hard\b', 'git reset --hard destroys work whose owner is unknown: preserve it first'),
]


def has_env(text):
    return any(not (m.group(1) or '').startswith('.example') for m in ENV.finditer(text))


def strip_quoted(cmd):
    # A commit message may name a forbidden command: test the command, not its quoted text.
    cmd = re.sub(r"<<-?\s*'?(\w+)'?.*?^\1$", ' ', cmd, flags=re.S | re.M)
    return re.sub(r'"(\\.|[^"\\])*"|\'[^\']*\'', '""', cmd)


def check(tool, inp):
    if tool in ('Bash', 'PowerShell'):
        cmd = inp.get('command', '')
        code = strip_quoted(cmd)
        if READ.search(code) and has_env(cmd):
            return WHY_ENV
        for pat, why in RULES:
            if re.search(pat, code):
                return why
    elif tool in ('Read', 'Edit', 'Write', 'NotebookEdit'):
        path = inp.get('file_path', '') or inp.get('notebook_path', '')
        if has_env(re.split(r'[\\/]', path)[-1]):
            return WHY_ENV
    return None


def selftest():
    bad = [('Bash', 'cat .env'), ('PowerShell', 'Get-Content C:\\proj\\.env.local'), ('Bash', "grep KEY '.env'"),
           ('Bash', 'source .env'), ('Bash', 'python -c "print(open(\'.env\').read())"'),
           ('Bash', 'git commit --no-verify -m x'), ('Bash', 'git push --force origin main'), ('Bash', 'git push -f'),
           ('Bash', 'git reset --hard HEAD~1')]
    good = [('Bash', 'cat .env.example'), ('Bash', 'git commit -m "never use --no-verify or cat .env"'),
            ('Bash', 'git push origin main'), ('Bash', 'python scripts/verify.py'), ('Bash', 'git reset --soft HEAD~1'),
            ('Bash', 'git check-ignore .env'), ('Bash', 'ls scripts')]
    for tool, cmd in bad:
        assert check(tool, {'command': cmd}), cmd
    for tool, cmd in good:
        assert not check(tool, {'command': cmd}), cmd
    for path in ('.env', 'D:\\p\\.env.production', '/srv/app/.env'):
        assert check('Read', {'file_path': path}) and check('Edit', {'file_path': path}), path
    for path in ('scripts/run.py', '.env.example', 'docs/environment.md'):
        assert not check('Read', {'file_path': path}), path


if __name__ == '__main__':
    if '--selftest' in sys.argv:
        selftest()
        print('guard selftest ok')
        sys.exit(0)
    try:
        data = json.load(sys.stdin)
        why = check(data.get('tool_name', ''), data.get('tool_input') or {})
    except Exception as e:  # allow-explicit-failure: a guard bug must not freeze every session; it is shown (exit 1)
        print(f'guard.py error (call allowed): {e}', file=sys.stderr)
        sys.exit(1)
    if why:
        print(f'Refused by scripts/guard.py: {why}', file=sys.stderr)
        sys.exit(2)
