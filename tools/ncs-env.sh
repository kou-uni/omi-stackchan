# NCS 2.9.0 のビルド環境（Nordic のツールチェーンを /opt/nordic に置かずに使う）
#   コンパイラ: ~/ncs/toolchains/b8efef2ad5/opt/zephyr-sdk
#   Python/west: ~/ncs/venv（Zephyr・NCS・MCUboot の requirements を入れたもの）
# 使い方: source tools/ncs-env.sh
TC=$HOME/ncs/toolchains/b8efef2ad5
export PATH="$HOME/ncs/venv/bin:$TC/opt/zephyr-sdk/arm-zephyr-eabi/bin:$PATH"
export ZEPHYR_TOOLCHAIN_VARIANT=zephyr
export ZEPHYR_SDK_INSTALL_DIR="$TC/opt/zephyr-sdk"
