#!/usr/bin/env python
from shi7.shi7 import *
import multiprocessing
import os
import numpy as np


def subsample_fastqs(path_fastqs, num_files=10, num_sequences=100):
    for i, path_fastq in enumerate(path_fastqs):
        with open(path_fastq) as fastq_inf:
            if i >= num_files:
                break
            fastq_gen = read_fastq(fastq_inf)
            yield limit_fastq(fastq_gen, num_sequences=num_sequences)


def limit_fastq(fastq_gen, num_sequences=100):
    for i in range(num_sequences):
        yield next(fastq_gen)


def get_seq_length_qual_scores(path_fastqs, output_path, num_files=10, num_sequences=1000):
    subsampled_fastqs = subsample_fastqs(path_fastqs, num_files=num_files, num_sequences=num_sequences)
    sequence_len_sum = 0.
    quality_sum = 0
    num_sequences = 0.

    # sequences = []
    # qualities = []
    for fastq_path, fastq_gen in zip(path_fastqs, subsampled_fastqs):
        with open(os.path.join(output_path, os.path.basename(fastq_path)), 'w') as outf:
            for header, sequence, quality in fastq_gen:
                outf.write("@%s\n%s\n+\n%s\n" % (header, sequence, quality))
                # sequences.append(sequences)
                # qualities.append(qualities)
                sequence_len_sum += len(sequence)
                quality_sum += sum([ord(i) for i in quality])
                num_sequences += 1.
    # Return (average length of sequences, average quality score)
    return sequence_len_sum/num_sequences, quality_sum/sequence_len_sum

# def get_all_fastq_seqs_qual(path_fastqs):
#     for i, path_fastq in enumerate(path_fastqs):
#         with open(path_fastq) as fastq_inf:
#             fastq_gen = read_fastq(fastq_inf)
#             yield next(fastq_gen)


def count_num_lines(path):
    with open(path) as path_inf:
        return sum(1 for line in path_inf)


def get_file_size(path):
    return os.path.getsize(path)


def check_sequence_name(path_R1, path_R2):
    with open(path_R1) as path_inf_R1, open(path_R2) as path_inf_R2:
        fastq_gen_R1 = read_fastq(path_inf_R1)
        fastq_gen_R2 = read_fastq(path_inf_R2)
        for gen_R1, gen_R2 in zip(fastq_gen_R1,fastq_gen_R2):
            title_R1, title_R2 = gen_R1[0], gen_R2[0]
            if len(title_R1) != len(title_R2):
                return False
            diff_idx = [i for i in range(len(title_R1)) if title_R1[i] != title_R2[i]]
            if len(diff_idx) != 1:
                return False
            if int(title_R2[diff_idx[0]]) - int(title_R1[diff_idx[0]]) != 1:
                return False
    return True


def detect_paired_end(path_fastqs):
    #path_fastqs = [f for f in path_fastqs if f.endswith('.fastq') or f.endswith('.fq')]
    if len(path_fastqs) % 2 == 1:
        return False
    path_fastqs = sorted(path_fastqs)
    path_R1_fastqs, path_R2_fastqs = path_fastqs[::2], path_fastqs[1::2]
    if len(path_R1_fastqs) != len(path_R2_fastqs) or len(path_R1_fastqs) < 1:
        return False
    R1_lines_num = []
    R2_lines_num = []
    R1_files_size = []
    R2_files_size = []
    seqs_name = []
    for path_R1_fastq in path_R1_fastqs:
        R1_lines_num.append(count_num_lines(path_R1_fastq))
        R1_files_size.append(get_file_size(path_R1_fastq))
    for path_R2_fastq in path_R2_fastqs:
        R2_lines_num.append(count_num_lines(path_R2_fastq))
        R2_files_size.append(get_file_size(path_R2_fastq))
    for path_R1_fastq, path_R2_fastq in zip(path_R1_fastqs, path_R2_fastqs):
        seqs_name.append(check_sequence_name(path_R1_fastq, path_R2_fastq))
    if not R1_lines_num == R2_lines_num or not R1_files_size == R2_files_size or False in seqs_name:
        return False
    return True


def get_directory_size(path):
    return sum([get_file_size(os.path.join(path, fastq)) for fastq in os.listdir(path)])


def remove_directory_contents(path):
    for f in os.listdir(path):
        os.remove(os.path.join(path, f))


def choose_axe_adaptors(path_subsampled_fastqs, output_path):
    adapters = ['Nextera', 'TruSeq2', 'TruSeq3', 'TruSeq3-2']
    threads = min(multiprocessing.cpu_count(),16)
    original_size = get_directory_size(os.path.dirname(path_subsampled_fastqs[0]))
    print('Original size of the subsampled_fastqs = ', original_size)
    best_size = original_size
    best_adap = None
    if detect_paired_end(path_subsampled_fastqs):
        print("Entering paired end ...")
        for adapter in adapters:
            axe_adaptors_paired_end(path_subsampled_fastqs, output_path, adapter, threads, shell=False)
            fastqs_path_size = get_directory_size(output_path)
            print(adapter, fastqs_path_size)
            if fastqs_path_size < best_size:
                best_size = fastqs_path_size
                best_adap = adapter
            remove_directory_contents(output_path)
    else:
        print("Entering single end ...")
        for adapter in adapters:
            axe_adaptors_single_end(path_subsampled_fastqs, output_path, adapter, threads, shell=False)
            fastqs_path_size = get_directory_size(output_path)
            print(adapter, fastqs_path_size)
            if fastqs_path_size < best_size:
                best_size = fastqs_path_size
                best_adap = adapter
            remove_directory_contents(output_path)

    if best_size < 0.995*original_size:
        return best_adap, best_size
    else:
        return None, original_size


def flash_is_stitchable(adapter_output_filenames, flash_output_path):
    num_threads = min(multiprocessing.cpu_count(),16)
    path_flash_fqs = flash(adapter_output_filenames, flash_output_path, max_overlap=700, min_overlap=20, allow_outies=True, threads=num_threads, shell=False)
    path_R1_fastqs, _ = split_fwd_rev(adapter_output_filenames)
    print('flash:', path_flash_fqs)
    print('original:', path_R1_fastqs)
    matched_count = 0
    for original_fq, flash_fq in zip(path_R1_fastqs, path_flash_fqs):
        print(count_num_lines(flash_fq), count_num_lines(original_fq))
        if count_num_lines(flash_fq) > count_num_lines(original_fq)*0.3:
            matched_count = matched_count + 1
    return matched_count/len(path_flash_fqs) >= 0.75

def flash_check_outies(flash_output_path):
    pass


def flash_check_cv(flash_output_path):
    hist_files = [os.path.join(flash_output_path, f) for f in os.listdir(flash_output_path) if f.endswith('.hist')]
    print(hist_files)
    for f in hist_files:
        freq_table = np.loadtxt(f)
        all_nums = [[row[0]]*int(row[1]) for row in freq_table]
        all_nums = sum(all_nums, [])
        coeff_var = np.std(all_nums)/np.mean(all_nums)
        print("CV =", coeff_var)
    # incomplete

