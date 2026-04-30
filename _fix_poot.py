import sys
sys.path.insert(0, r'D:\injoinic--job\自动化测试平台开发\自动化测试平台')
lines = open(r'D:\injoinic--job\自动化测试平台开发\自动化测试平台\test_cases\output_tests\OutputPowerOnOffTest.py', encoding='utf-8').readlines()

for i, l in enumerate(lines):
    print(i+1, repr(l))
    if i >= 455:
        break
