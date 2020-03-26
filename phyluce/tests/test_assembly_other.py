#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
(c) 2018 Brant Faircloth || http://faircloth-lab.org/

All rights reserved.

This code is distributed under a 3-clause BSD license. Please see
LICENSE.txt for more information.

Created on 06 July 2018 15:37 CDT (-0500)
"""

import os
import shutil
import subprocess
import configparser

# from phyluce.tests.common import get_contig_lengths_and_counts

import pytest
from Bio import SeqIO

import pdb


@pytest.fixture(scope="module")
def o_dir(request):
    directory = os.path.join(
        request.config.rootdir, "phyluce", "tests", "test-observed"
    )
    os.mkdir(directory)

    def clean():
        shutil.rmtree(directory)

    request.addfinalizer(clean)
    return directory


@pytest.fixture(scope="module")
def e_dir(request):
    directory = os.path.join(
        request.config.rootdir, "phyluce", "tests", "test-expected"
    )
    return directory


@pytest.fixture(scope="module")
def conf_dir(request):
    directory = os.path.join(
        request.config.rootdir, "phyluce", "tests", "test-conf"
    )
    return directory


@pytest.fixture(scope="module")
def raw_dir(request):
    directory = os.path.join(
        request.config.rootdir,
        "phyluce",
        "tests",
        "test-expected",
        "raw-reads-short",
        "alligator-mississippiensis",
    )
    return directory


def get_match_count_cmd(
    o_dir, e_dir, conf_dir, output_config, request, incomplete=False
):
    program = "bin/assembly/phyluce_assembly_get_match_counts"
    cmd = [
        os.path.join(request.config.rootdir, program),
        "--locus-db",
        os.path.join(e_dir, "probe-match", "probe.matches.sqlite"),
        "--taxon-list-config",
        os.path.join(conf_dir, "taxon-set.conf"),
        "--taxon-group",
        "all",
        "--output",
        output_config,
        "--log-path",
        o_dir,
    ]
    if not incomplete:
        return cmd
    else:
        cmd.append("--incomplete-matrix")
        return cmd


def test_get_fastq_lengths(o_dir, e_dir, raw_dir, request):
    program = "bin/assembly/phyluce_assembly_get_fastq_lengths"
    cmd = [
        os.path.join(request.config.rootdir, program),
        "--input",
        raw_dir,
        "--csv",
    ]
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    stdout, stderr = proc.communicate()
    stdout_str = stdout.decode("utf-8")
    assert (
        stdout_str
        == "All files in dir with alligator-mississippiensis-READ2.fastq.gz,7404,677024,91.44030253916802,0.1993821226016458,40,100,100.0\n"
    )


def test_get_match_counts_complete(o_dir, e_dir, conf_dir, request):
    output_config = os.path.join(o_dir, "taxon-set.conf")
    cmd = get_match_count_cmd(o_dir, e_dir, conf_dir, output_config, request)
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    stdout, stderr = proc.communicate()
    obs_config = configparser.RawConfigParser(allow_no_value=True)
    obs_config.optionxform = str
    obs_config.read(output_config)
    expected_config = os.path.join(e_dir, "taxon-set.complete.conf")
    exp_config = configparser.RawConfigParser(allow_no_value=True)
    exp_config.optionxform = str
    exp_config.read(expected_config)
    assert obs_config == exp_config


def test_get_match_counts_incomplete(o_dir, e_dir, conf_dir, request):
    output_config = os.path.join(o_dir, "taxon-set.conf")
    cmd = get_match_count_cmd(
        o_dir, e_dir, conf_dir, output_config, request, incomplete=True
    )
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    stdout, stderr = proc.communicate()
    obs_config = configparser.RawConfigParser(allow_no_value=True)
    obs_config.optionxform = str
    obs_config.read(output_config)
    expected_config = os.path.join(e_dir, "taxon-set.incomplete.conf")
    exp_config = configparser.RawConfigParser(allow_no_value=True)
    exp_config.optionxform = str
    exp_config.read(expected_config)
    assert obs_config == exp_config


def get_fastas_cmd(o_dir, e_dir, o_file, request, incomplete=False):
    program = "bin/assembly/phyluce_assembly_get_fastas_from_match_counts"
    cmd = [
        os.path.join(request.config.rootdir, program),
        "--locus-db",
        os.path.join(e_dir, "probe-match", "probe.matches.sqlite"),
        "--contigs",
        os.path.join(e_dir, "spades", "contigs"),
        "--locus-db",
        os.path.join(e_dir, "probe-match", "probe.matches.sqlite"),
        "--match-count-output",
        os.path.join(e_dir, "taxon-set.complete.conf"),
    ]
    if not incomplete:
        cmd.extend(["--output", o_file, "--log-path", o_dir])
    else:
        cmd.extend(
            [
                "--output",
                o_file,
                "--log-path",
                o_dir,
                "--incomplete-matrix",
                os.path.join(o_dir, "taxon-set.incomplete"),
            ]
        )
    return cmd


def test_get_fastas_complete(o_dir, e_dir, request):
    o_file = os.path.join(o_dir, "taxon-set.complete.fasta")
    cmd = get_fastas_cmd(o_dir, e_dir, o_file, request, incomplete=False)
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    stdout, stderr = proc.communicate()
    # read in the new outfile
    observed_sequences = SeqIO.to_dict(SeqIO.parse(o_file, "fasta"))
    # read in the expected outfile
    expected_sequences = SeqIO.to_dict(
        SeqIO.parse(os.path.join(e_dir, "taxon-set.complete.fasta"), "fasta")
    )
    # compare
    for k, v in observed_sequences.items():
        assert v.seq == expected_sequences[k].seq


def test_get_fastas_incomplete(o_dir, e_dir, conf_dir, request):
    o_file = os.path.join(o_dir, "taxon-set.incomplete.fasta")
    cmd = get_fastas_cmd(o_dir, e_dir, o_file, request, incomplete=True)
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    stdout, stderr = proc.communicate()
    # read in the new outfile
    observed_sequences = SeqIO.to_dict(SeqIO.parse(o_file, "fasta"))
    # read in the expected outfile
    expected_sequences = SeqIO.to_dict(
        SeqIO.parse(os.path.join(e_dir, "taxon-set.incomplete.fasta"), "fasta")
    )
    # compare
    for k, v in observed_sequences.items():
        assert v.seq == expected_sequences[k].seq


"""
def test_explode_get_fastas_file(o_dir):
    program = "bin/assembly/phyluce_assembly_explode_get_fastas_file"
    cmd = [
        os.path.join(ROOTDIR, program),
        "--config",
        a_conf,
        "--cores",
        "1",
        "--output",
        "{}".format(os.path.join(o_dir, "spades")),
        "--log-path",
        o_dir,
    ]
"""
