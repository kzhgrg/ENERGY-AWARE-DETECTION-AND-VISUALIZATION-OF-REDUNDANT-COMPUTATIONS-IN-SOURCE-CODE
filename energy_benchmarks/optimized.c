#include <stdio.h>
#include <stdint.h>
int main(void) {
    volatile uint64_t sink=0;
    for (uint64_t repeat=0;repeat<180000000ULL;repeat++) {
        uint64_t x=repeat & 1023ULL;
        uint64_t a=x*x + 3ULL*x;
        sink += a+a;
    }
    printf("%llu\n",(unsigned long long)sink);
    return 0;
}
