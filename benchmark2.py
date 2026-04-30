import timeit
import re

text = "The temperature today is 25°C, and it is going to be a bit sunny."

def test_uncompiled():
    # Calling re.findall repeatedly inside a loop clears out any internal caching
    temp_patterns = [
        r'(\d+)\s*°[CF]',
        r'(\d+)\s*degrees',
        r'temperature[:\s]*(\d+)',
    ]
    # We simulate many calls because usually content is large, or loop runs multiple times
    for i in range(100):
        for pattern in temp_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)

RE_TEMP_PATTERNS = [
    re.compile(r'(\d+)\s*°[CF]', re.IGNORECASE),
    re.compile(r'(\d+)\s*degrees', re.IGNORECASE),
    re.compile(r'temperature[:\s]*(\d+)', re.IGNORECASE),
]

def test_compiled():
    for i in range(100):
        for pattern in RE_TEMP_PATTERNS:
            matches = pattern.findall(text)

uncompiled_time = timeit.timeit(test_uncompiled, number=1000)
compiled_time = timeit.timeit(test_compiled, number=1000)

print(f"Uncompiled Time: {uncompiled_time:.6f} s")
print(f"Compiled Time: {compiled_time:.6f} s")
print(f"Improvement: {(uncompiled_time - compiled_time) / uncompiled_time * 100:.2f}%")
