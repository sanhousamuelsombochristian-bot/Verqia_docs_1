import re, io, os
from collections import defaultdict

d = r'C:\Users\HP\Links\verqia-docs'


def rd(n):
    return io.open(os.path.join(d, n), encoding='utf-8').read()


TOK = re.compile(r'`([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+)`')
src = defaultdict(set)


def add(code, tag):
    src[code].add(tag)


inv = rd('INVARIANTS_V1.md')
for line in inv.split('\n'):
    if line.startswith(('| **5 Erreurs**', '| **Erreurs**', '| Erreurs |')):
        for t in TOK.findall(line):
            add(t, 'INV')

rule = rd('RULE_ENGINE_V1.md')
s5 = rule[rule.index('## 5. Validation statique'):rule.index('## 6. La décision')]
for line in s5.split('\n'):
    if line.startswith('|'):
        cells = [c for c in line.split('|') if c.strip()]
        if cells:
            for t in TOK.findall(cells[-1]):
                if t.startswith('DEFINITION_'):
                    add(t, 'RULE')
for line in rule.split('\n'):
    if line.startswith("Erreurs d'autorisation"):
        for t in TOK.findall(line):
            add(t, 'RULE')
add('SUBJECT_NOT_FOUND', 'RULE')

for t in ['TEMPLATE_UNAVAILABLE', 'SUBJECT_NOT_FOUND', 'ACTION_LEVEL_INVALID', 'ACTION_LEVEL_BELOW_MINIMUM']:
    add(t, 'COL')
for t in ['AUTOMATION_PRECONDITIONS_NOT_MET', 'ENROLLMENT_PREVIEW_STALE', 'AUTOMATION_SET_LOOP_DETECTED',
          'EXECUTION_RATE_LIMITED', 'DEFINITION_ACTION_SUBJECT_MISMATCH']:
    add(t, 'AUT')
for t in ['EVENT_SCHEMA_INVALID', 'EVENT_PAYLOAD_NOT_WHITELISTED', 'CAUSATION_DEPTH_EXCEEDED', 'CHANNEL_NOT_ENABLED',
          'FACT_UNKNOWN_NAME', 'DEFINITION_NOT_FOUND', 'ENGINE_INTERNAL_ERROR', 'SUBJECT_NOT_FOUND', 'SERIALIZATION_FAILURE',
          'INSUFFICIENT_ROLE', 'INVALID_TRANSITION', 'IDEMPOTENCY_KEY_REUSED', 'CONCURRENT_MODIFICATION', 'TEMPLATE_UNAVAILABLE']:
    add(t, 'ENG')

for t in ['DB_INVARIANT_VIOLATED', 'TENANT_CONTEXT_MISSING', 'LOCK_ORDER_VIOLATION']:
    add(t, 'ARCH')

# ---- classification ----
FORBIDDEN = {'INSUFFICIENT_ROLE', 'OVERRIDE_ROLE_INSUFFICIENT', 'OVERRIDE_NOT_ALLOWED', 'SELF_APPROVAL_FORBIDDEN', 'APPROVER_NOT_ELIGIBLE'}
BUSINESS = {'ACTION_APPROVAL_REQUIRED', 'IMPORT_APPROVAL_REQUIRED', 'ACTION_LEVEL_REGRESSION', 'ACTION_LEVEL_BELOW_MINIMUM',
            'ACTION_MAX_ATTEMPTS_REACHED', 'HOLD_OVERLAP', 'TEMPLATE_UNAVAILABLE', 'CHANNEL_NOT_ENABLED',
            'AUTOMATION_PRECONDITIONS_NOT_MET', 'AUTOMATION_SET_LOOP_DETECTED', 'OVERRIDE_ORIGIN_NOT_MANUAL'}
RETRY = {'CONCURRENT_MODIFICATION', 'SERIALIZATION_FAILURE', 'EXECUTION_RATE_LIMITED'}


def classify(c):
    if c in ('DB_INVARIANT_VIOLATED', 'TENANT_CONTEXT_MISSING', 'LOCK_ORDER_VIOLATION'):
        return 'INTERNAL'
    if c.endswith('_MODEL_UNKNOWN'):
        return 'INTERNAL'
    if c == 'EVENT_PAYLOAD_NOT_WHITELISTED':
        return 'VALIDATION'
    if 'INVALID_TRANSITION' in c or 'DUPLICATE_' in c:
        return 'CONFLICT'
    if c.endswith('_NOT_FOUND'):
        return 'NOT_FOUND'
    if c in FORBIDDEN:
        return 'FORBIDDEN'
    if c == 'EXECUTION_RATE_LIMITED':
        return 'RATE_LIMITED'
    if c == 'ENGINE_INTERNAL_ERROR':
        return 'INTERNAL'
    if c in BUSINESS:
        return 'BUSINESS_RULE'
    if c.endswith('_REASON_REQUIRED') or c.endswith('_COMMENT_REQUIRED'):
        return 'VALIDATION'
    if (c in ('CONCURRENT_MODIFICATION', 'SERIALIZATION_FAILURE', 'INVALID_TRANSITION', 'IDEMPOTENCY_KEY_REUSED', 'ENROLLMENT_PREVIEW_STALE')
            or '_TAKEN' in c or '_ALREADY_' in c or 'IN_PROGRESS' in c or c.endswith('_LOCKED') or c.endswith('_CONFLICT')
            or c.endswith('_NOT_ACTIVE') or c.endswith('_NOT_READY') or c in ('IMPORT_BATCH_COMMITTED',) or c.startswith('CUSTOMER_INACTIVE') and False):
        return 'CONFLICT'
    if (c.startswith('DEFINITION_') or c.endswith('_INVALID') or c.endswith('_INVALID_VALUE') or c.endswith('_MISMATCH')
            and not c.startswith('ALLOCATION_')) and not c.startswith('ALLOCATION_'):
        return 'VALIDATION'
    if c.endswith('_UNKNOWN') or c.endswith('_UNKNOWN_NAME') or c.endswith('_EXCEEDED') and c.startswith('CAUSATION'):
        return 'VALIDATION' if c != 'CAUSATION_DEPTH_EXCEEDED' else 'BUSINESS_RULE'
    return 'BUSINESS_RULE'


HTTP = {'VALIDATION': '400/422', 'BUSINESS_RULE': '422', 'NOT_FOUND': '404', 'FORBIDDEN': '403', 'CONFLICT': '409',
        'RATE_LIMITED': '429', 'TRANSIENT': '503', 'INTERNAL': '500'}
rows = []
for code in sorted(src):
    cl = classify(code)
    rows.append((code, cl, HTTP[cl], 'oui' if code in RETRY else 'non', ', '.join(sorted(src[code]))))

by = defaultdict(int)
for r in rows:
    by[r[1]] += 1
out = ["## Annexe A · Catalogue des erreurs (généré)", "",
       "Généré à partir des lignes « Erreurs » des Invariants, du tableau de validation du Rule Engine, des passes Collection, Automation et de ce document. **La classification est une proposition à relire** (EC4).",
       "",
       "Sources : `INV` Invariants · `RULE` Rule Engine · `COL` Collection Engine · `AUT` Automation Engine · `ENG` Engine Contracts · `ARCH` Architecture technique (erreurs techniques internes).",
       "", "Répartition : " + " · ".join("%s %d" % (k, v) for k, v in sorted(by.items())) + " — **total %d codes**." % len(rows), "",
       "| Code | Classe | HTTP | Nouvelle tentative | Sources |", "|---|---|---|---|---|"]
out += ["| `%s` | %s | %s | %s | %s |" % r for r in rows]
annex = "\n".join(out) + "\n"

p = os.path.join(d, 'ENGINE_CONTRACTS_V1.md')
c = rd('ENGINE_CONTRACTS_V1.md')
if '## Annexe A' in c:
    c = c[:c.index('## Annexe A')].rstrip('\n') + '\n'
c = c.rstrip('\n') + "\n\n---\n\n" + annex
io.open(p, 'w', encoding='utf-8').write(c)

# ---- verification: codes cités dans les lignes « Erreurs » du document principal ----
main = c[:c.index('## Annexe A')]
cited = set()
for line in main.split('\n'):
    if line.startswith('| **Erreurs**'):
        cited |= set(TOK.findall(line))
missing = sorted(t for t in cited if t not in src)
print("codes au catalogue:", len(rows), "| par classe:", dict(by))
print("codes cites dans les lignes Erreurs d'EC-xx absents du catalogue:", missing)
print("codes tries au hasard:", [r[0] + '=' + r[1] for r in rows[::15]])
