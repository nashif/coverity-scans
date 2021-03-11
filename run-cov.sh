#!/bin/bash

set -x
# run this script in a zephyr tree. It will generate a file named coverity.tgz
# that you will need to upload to coverity server.


COV_BIN=/home/anashif/bin/cov-analysis-linux64-2020.09/bin

COV_BUILD_DIR=/tmp/cov-build
COV_INT=${COV_BUILD_DIR}/cov-int
SAN_OPT="-b -j 64"
COV_CONF=${COV_BIN}/cov-configure
COV_BUILD=${COV_BIN}/cov-build

# define both COVERITY_TOKEN and COVERITY_USER in the file blow
coverity_answer_file=$HOME/.coverityrc

[ -f ${coverity_answer_file} ] &&  . ${coverity_answer_file}

mkdir -p coverity
mkdir -p ${COV_BUILD_DIR}
rm -rf ${COV_INT}
export USE_CCACHE=0

source zephyr-env.sh
export ZEPHYR_TOOLCHAIN_VARIANT=zephyr

# Build for native_posix/x86_64 with host compiler

function build_with_host_compiler() {
	board=$1
	${COV_CONF} --comptype gcc --compiler gcc --template
	${COV_BUILD} --dir ${COV_INT} twister -x=USE_CCACHE=0 -p ${board} ${SAN_OPT} --log-file coverity/twister-${board}.log
}

TAGS_IN="benchmark userspace kernel tinycrypt cmsis_rtos posix interrupt test_framework"

for t in ${TAGS_IN}; do
	TAGS_IN_OPT="${TAGS_IN_OPT} -t ${t}"
	TAGS_OUT_OPT="${TAGS_OUT_OPT} -e ${t}"
done

function build_cross() {

	ARCHES="x86 arm arc riscv32 xtensa nios"

	for ARCH in ${ARCHES};  do
		# First we collect test cases with platforms that provide full
		# coverage on kernel tests
		if [ $ARCH = "x86" ]; then
			COMPILER=x86_64-zephyr-elf-gcc
			twister -N -p qemu_x86 ${TAGS_IN_OPT} --save-tests coverity/tests_001.txt
			COVERAGE="-p qemu_x86 -p up_squared -p ehl_crb"
		elif [ $ARCH = "arm" ]; then
			COMPILER=arm-zephyr-eabi-gcc
			twister -N -p frdm_k64f ${TAGS_IN_OPT} --save-tests coverity/tests_001.txt
			COVERAGE="-p nrf52840dk_nrf52840 -p frdm_k64f -p atsamd21_xpro -p disco_l475_iot1 -p qemu_cortex_a53 -p qemu_cortex_m0 -p qemu_cortex_m3 -p qemu_cortex_r5 -p reel_board -p sam_e70_xplained -p mimxrt1050_evk -p mimxrt1010_evk -p mec15xxevb_assy6853 -p mec1501modular_assy6885 -p nrf5340pdk_nrf5340 -p nucleo_l4r5zi -p nucleo_f767zi -p npcx7m6fb_evb -p nrf5340dk_nrf5340_cpuapp"
		elif [ $ARCH = "arc" ]; then
			COVERAGE="-p iotdk"
			COMPILER=${ARCH}-zephyr-elf-gcc
			twister -N -a ${ARCH} ${TAGS_IN_OPT} --save-tests coverity/tests_001.txt
		elif [ $ARCH = "nios2" ]; then
			COVERAGE="-p qemu_nios2"
			COMPILER=${ARCH}-zephyr-elf-gcc
			twister -N -a ${ARCH} ${TAGS_IN_OPT} --save-tests coverity/tests_001.txt
		elif [ $ARCH = "xtensa" ]; then
			COVERAGE="-p qemu_xtensa -p intel_adsp_cavs15"
			COMPILER=${ARCH}-zephyr-elf-gcc
			twister -N -a ${ARCH} ${TAGS_IN_OPT} --save-tests coverity/tests_001.txt
		elif [ $ARCH = "riscv32" ]; then
			COVERAGE="-p qemu_riscv32"
			COMPILER=${ARCH}-zephyr-elf-gcc
			twister -N -a ${ARCH} ${TAGS_IN_OPT} --save-tests coverity/tests_001.txt
		else
			COVERAGE="-a ${ARCH} --all"
			COMPILER=${ARCH}-zephyr-elf-gcc
			twister -N -a ${ARCH} ${TAGS_IN_OPT} --save-tests coverity/tests_001.txt
		fi
		# Then we lists all tests on all remaining platform excluding
		# common tests.

		twister -N ${COVERAGE} ${TAGS_OUT_OPT} --save-tests coverity/tests_002.txt
		for b in ${EXCLUDE_B}; do
			grep -v ${b} coverity/tests_002.txt > coverity/tmp_out
			cp coverity/tmp_out coverity/tests_002.txt
		done
		# Here we create the final test manifest

		tail -n +2 coverity/tests_002.txt > coverity/tests_002_2.txt

		cat coverity/tests_001.txt coverity/tests_002_2.txt > coverity/tests.txt

		${COV_CONF} --comptype gcc --compiler ${COMPILER} --template
		${COV_BUILD} --dir ${COV_INT} twister -N --load-tests coverity/tests.txt -a ${ARCH} ${SAN_OPT} --log-file coverity/twister-${ARCH}.log 
		rm -f coverity/tests_001.txt coverity/tests_002.txt
		rm -f coverity/tests.txt
	done
}

build_cross
build_with_host_compiler native_posix


VERSION=$(git describe)

pushd ${COV_BUILD_DIR}
tar -czvf coverity-${VERSION}.tgz cov-int
popd

echo "Done. Please submit the archive to Coverity Scan now."

if true; then
	curl --form token=$COVERITY_TOKEN \
		--form email=$COVERITY_USER \
		--form file=@${COV_BUILD_DIR}/coverity-${VERSION}.tgz \
		--form version="${VERSION}" \
		--form description="${VERSION}" \
		https://scan.coverity.com/builds?project=Zephyr
fi

rm -rf twister-out*
