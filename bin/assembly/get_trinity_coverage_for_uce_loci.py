#!/usr/bin/env python
# encoding: utf-8
"""
File: get_trinity_coverage_for_uce_loci.py
Author: Brant Faircloth

Created by Brant Faircloth on 01 October 2013 14:10 PDT (-0700)
Copyright (c) 2013 Brant C. Faircloth. All rights reserved.

Description:

"""

import os
import re
import sys
import gzip
import glob
import numpy
import sqlite3
import argparse
import ConfigParser

from phyluce.helpers import FullPaths, CreateDir, is_file, is_dir
from phyluce.bwa import *
from phyluce.log import setup_logging

import pdb


def get_args():
    """Get arguments from CLI"""
    parser = argparse.ArgumentParser(
            description="""Given the input file generated by get_trinity_coverage, extract the values for UCE loci""")
    parser.add_argument(
        "--assemblies",
        required=True,
        action=FullPaths,
        help="""The directory containing the assemblies"""
    )
    parser.add_argument(
        "--match-count-output",
        required=True,
        type=is_file,
        action=FullPaths,
        help="""The output file containing taxa and loci in complete/incomplete matrices generated by get_match_counts.py."""
    )
    parser.add_argument(
        "--locus-db",
        required=True,
        type=is_file,
        action=FullPaths,
        help="""The SQL database file holding probe matches to targeted loci (usually "lastz/probe.matches.sqlite")."""
    )
    parser.add_argument(
        "--output",
        required=True,
        action=CreateDir,
        help="""The output directory to hold the UCE coverage files"""
    )
    parser.add_argument(
        "--verbosity",
        type=str,
        choices=["INFO", "WARN", "CRITICAL"],
        default="INFO",
        help="""The logging level to use"""
    )
    parser.add_argument(
        "--log-path",
        action=FullPaths,
        type=is_dir,
        default=None,
        help="""The path to a directory to hold logs."""
    )
    return parser.parse_args()


def get_match_count_loci(log, config):
    log.info("Fetching loci from {}".format(os.path.basename(config)))
    conf = ConfigParser.ConfigParser(allow_no_value=True)
    conf.optionxform = str
    conf.read(config)
    return [locus[0] for locus in conf.items('Loci')]


def get_sqlite_loci_for_taxon(log, db, cur, organism, loci):
    log.info("Fetching contig names from from {}".format(os.path.basename(db)))
    organism = os.path.basename(organism).replace('-', '_')
    # create list of loci
    st = "SELECT uce, {0} FROM match_map WHERE uce IN ({1}) AND {0} IS NOT NULL"
    query = st.format(organism, ','.join(["'{0}'".format(i) for i in loci]))
    cur.execute(query)
    data = cur.fetchall()
    data_dict = {}
    for locus in data:
        uce = locus[0]
        contig = re.sub("\\(\\-\\)|\\(\\+\\)$", "", locus[1])
        data_dict[contig] = uce
    return data_dict


def create_per_locus_coverage_file(log, output, assembly, organism, locus_map, locus_map_names):
    log.info("Generating per-contig coverage file and interval list for UCE loci.")
    sq_header_pth = os.path.join(assembly, "Trinity.dict")
    interval_list_pth = os.path.join(output, "{}-UCE-matches-interval.list".format(organism))
    coverage_untrimmed = []
    coverage_trimmed = []
    trimmed_length = []
    count = 0
    with open(os.path.join(output, "{}-UCE-per-contig-coverage.txt".format(organism)), 'w') as outf:
        with open(interval_list_pth, 'w') as interval_list:
            with open(os.path.join(assembly, "{}-TRIMMED-per-contig-coverage.txt".format(organism)), 'rU') as infile:
                with open(sq_header_pth, 'rb') as sq_header:
                    interval_list.writelines(sq_header)
                    header = infile.readline()
                    outf.write(header)
                    for line in infile:
                        ls = line.split()
                        contig = ls[0]
                        if contig in locus_map_names:
                            ls[0] = locus_map[contig]
                            outf.write("{}\n".format(
                                "\t".join(ls)
                            ))
                            # keep track of contig count
                            count += 1
                            # keep track of trimmed contig length
                            trimmed_length.append(float(ls[-2]))
                            # also keep mean, trimmed coverage
                            coverage_untrimmed.append(float(ls[2]))
                            coverage_trimmed.append(float(ls[-1]))
                            # also create an interval file for on-target calcs w/ Picard
                            # assume all are in + direction
                            interval_list.write("{}\t1\t{}\t+\t{}\n".format(
                                contig,
                                ls[1],
                                ls[0]
                            ))
    results = {
        "interval_list":interval_list_pth,
        "count":count,
        "mean_length_trimmed":numpy.mean(trimmed_length),
        "mean_untrim_cov":numpy.mean(coverage_untrimmed),
        "mean_trim_cov":numpy.mean(coverage_trimmed)
    }
    return results


def create_per_base_coverage_file(log, output, assembly, organism, locus_map, locus_map_names):
    log.info("Generating per-base coverage file for UCE loci.")
    with gzip.open(os.path.join(output, "{}-UCE-per-base-coverage.txt.gz".format(organism)), 'w') as outf:
        with gzip.open(os.path.join(assembly, "{}-TRIMMED-per-base-coverage.txt.gz".format(organism))) as infile:
            header = infile.readline()
            outf.write(header)
            for line in infile:
                ls = line.split()
                contig, pos = ls[0].split(":")
                if contig in locus_map_names:
                    locus = locus_map[contig]
                    ls[0] = "{}:{}".format(locus, pos)
                    outf.write("{}\n".format(
                        "\t".join(ls)
                    ))


def main():
    # get args and options
    args = get_args()
    # setup logging
    log, my_name = setup_logging(args)
    log.info("Creating the output directory")
    # get the input data
    log.info("Fetching input filenames")
    assemblies = glob.glob(os.path.join(args.assemblies, "*"))
    loci = get_match_count_loci(log, args.match_count_output)
    # setup database connection
    conn = sqlite3.connect(args.locus_db)
    cur = conn.cursor()
    for assembly in assemblies:
        organism = os.path.basename(assembly)
        reference = os.path.join(assembly, "Trinity.fasta")
        bams = glob.glob(os.path.join(assembly, "*.bam"))
        try:
            assert len(bams) == 1
            bam = bams[0]
        except:
            raise IOError("There appears to be more than one BAM file for {}".format(organism))
        # pretty print taxon status
        text = " Processing {} ".format(organism)
        log.info(text.center(65, "-"))
        locus_map = get_sqlite_loci_for_taxon(log, args.locus_db, cur, organism, loci)
        locus_map_names = set(locus_map.keys())
        create_per_base_coverage_file(log, args.output, assembly, organism, locus_map, locus_map_names)
        coverages_dict = create_per_locus_coverage_file(log, args.output, assembly, organism, locus_map, locus_map_names)
        # pass the same intervals as targets and base - we don't care that much here about bait performance
        hs_metrics_file = picard_calculate_hs_metrics(log, organism, args.output, reference, bam, coverages_dict["interval_list"], coverages_dict["interval_list"])
        on_target_dict = picard_get_percent_reads_on_target(log, hs_metrics_file, organism)
        log.info("\t{} contigs, mean trimmed length = {:.1f}, mean trimmed coverage = {:.1f}x, unique reads aligned = {:.1f}%, on-target bases = {:.1f}%".format(
            coverages_dict["count"],
            coverages_dict["mean_length_trimmed"],
            coverages_dict["mean_trim_cov"],
            float(on_target_dict["PCT_PF_UQ_READS_ALIGNED"]) * 100,
            float(on_target_dict["PCT_SELECTED_BASES"]) * 100
        ))
    # end
    text = " Completed {} ".format(my_name)
    log.info(text.center(65, "="))

if __name__ == '__main__':
    main()
