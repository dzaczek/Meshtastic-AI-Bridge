import time
import re

content = "Some fake content " * 1000 + "<h1>Headline</h1>" * 10

def test_uncompiled():
    patterns = {'headline': [r'<h[1-3][^>]*>([^<]+)</h[1-3]>']}
    start = time.time()
    for _ in range(1000):
        for label, pats in patterns.items():
            for pat in pats:
                matches = re.findall(pat, content, re.IGNORECASE)
    end = time.time()
    return end - start

compiled_patterns = {'headline': [re.compile(r'<h[1-3][^>]*>([^<]+)</h[1-3]>', re.IGNORECASE)]}

def test_compiled():
    start = time.time()
    for _ in range(1000):
        for label, pats in compiled_patterns.items():
            for pat in pats:
                matches = pat.findall(content)
    end = time.time()
    return end - start

t1 = test_uncompiled()
t2 = test_compiled()

print(f"Uncompiled: {t1:.4f}s")
print(f"Compiled: {t2:.4f}s")
print(f"Improvement: {(t1-t2)/t1*100:.2f}%")
