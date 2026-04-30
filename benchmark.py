import timeit
import re

text = "The temperature today is 25°C, and it is going to be a bit sunny." * 1000

def test_uncompiled():
    temp_patterns = [
        r'(\d+)\s*°[CF]',  # 25°C or 77°F
        r'(\d+)\s*degrees',  # 25 degrees
        r'temperature[:\s]*(\d+)',  # temperature: 25
    ]
    for pattern in temp_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)

RE_TEMP_PATTERNS = [
    re.compile(r'(\d+)\s*°[CF]', re.IGNORECASE),
    re.compile(r'(\d+)\s*degrees', re.IGNORECASE),
    re.compile(r'temperature[:\s]*(\d+)', re.IGNORECASE),
]

def test_compiled():
    for pattern in RE_TEMP_PATTERNS:
        matches = pattern.findall(text)

uncompiled_time = timeit.timeit(test_uncompiled, number=1000)
compiled_time = timeit.timeit(test_compiled, number=1000)

print(f"Uncompiled Time: {uncompiled_time:.6f} s")
print(f"Compiled Time: {compiled_time:.6f} s")
print(f"Improvement: {(uncompiled_time - compiled_time) / uncompiled_time * 100:.2f}%")
