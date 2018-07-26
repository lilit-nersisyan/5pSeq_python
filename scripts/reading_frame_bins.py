import numpy as np
from plastid import GTF2_TranscriptAssembler, GFF3_TranscriptAssembler, Transcript, GenomicSegment, BAMGenomeArray, FivePrimeMapFactory
import dill
import matplotlib
import matplotlib.pyplot as plt
import os
import argparse
import sys
import multiprocessing
from multiprocessing import Process, Pool
import math
from math import gcd


def create_assembly_dill(annotation_file):
    if annotation_file.endswith("gtf"):
        gtf_file = list(GTF2_TranscriptAssembler(
            annotation_file, return_type=Transcript))
        dill.dump(gtf_file, open(global_args.output_dir +
                                 annotation_file[:-4].split("/")[-1] + ".sav", "wb"))
    elif annotation_file.endswith("gff"):
        gff_file = list(GFF3_TranscriptAssembler(
            annotation_file, return_type=Transcript))
        dill.dump(gff_file, open(global_args.output_dir +
                                 annotation_file[:-4].split("/")[-1] + ".sav", "wb"))


def extend_gtf_frame(pickle):

    pickle_path = global_args.output_dir + \
        global_args.annotation_file[:-4].split("/")[-1] + ".sav"

    if os.path.isfile(pickle_path) == False:
        create_assembly_dill(global_args.annotation_file)
    gtf_coords_file = list(dill.load(open(pickle_path, "rb")))

    for transcript in gtf_coords_file:
        span = transcript.spanning_segment
        new_region = GenomicSegment(
            span.chrom, span.start - global_args.offset, span.start, span.strand)
        new_region_2 = GenomicSegment(
            span.chrom, span.end, span.end + global_args.offset, span.strand)
        transcript.add_segments(new_region, new_region_2)
        yield transcript


def allowed_transcript_ids(filename):
    try:
        with open(filename, "r") as gene_list_file:
            return gene_list_file.read().splitlines()
    except:
        return list()


def fetch_vectors(filenames):

    allowed_ids = set(allowed_transcript_ids(global_args.gene_set))
    alignments = BAMGenomeArray(filenames, mapping=FivePrimeMapFactory())
    print("Genomes loaded!")

    except_count = 0
    count_vectors = []

    for transcript in extend_gtf_frame(global_args.annotation_file):
        if any([transcript.attr.get('Name') in allowed_ids, transcript.get_name() in allowed_ids]):
            try:
                value_array = transcript.get_counts(alignments)
                if np.sum(value_array) > global_args.cutoff:
                    count_vectors.append(value_array)

            except ValueError:
                except_count += 1

    print("Vectors retrieved!")
    print("Removed %i transcripts!" % except_count)

    tri_offset = global_args.offset / 3
    count_vectors = list(map(lambda x: np.reshape(x, (-1, 3)), count_vectors))
    bin_list = [[] for x in range(global_args.bins+2)]
    bin_size_list = []
    for vector in count_vectors:
        bin_size = ((vector.shape[0]-tri_offset*2) // global_args.bins) + \
            ((vector.shape[0]-tri_offset*2) % global_args.bins > 0)
        bin_size_list.append(bin_size)
        bin_list[0].append(vector[:tri_offset])
        bin_list[-1].append(vector[-tri_offset:])
        for ind in range(1, global_args.bins + 1):
            bin_list[ind].append(
                vector[(tri_offset)+bin_size*(ind-1):tri_offset+bin_size*ind])
    lcm = 1
    for i in bin_size_list:
        lcm = lcm*i/gcd(lcm, i)

    for bins in bin_list[(1, -1)]:
        bins = [(np.sum(np.vstack(x[0]), axis=0) for x in bins), (np.sum(np.vstack(x[1]), axis=0) for x in bins), (np.sum(np.vstack(x[2]), axis=0) for x in bins)]

    for bins in bin_list[1:-2]:
        for frames in bins:
            frames = np.repeat(frames.T, lcm/frames.shape[0])
        bins = [(np.sum(np.vstack(x[0]), axis=0) for x in bins), (np.sum(np.vstack(x[1]), axis=0) for x in bins), (np.sum(np.vstack(x[2]), axis=0) for x in bins)]

    return bin_list


def plot_results(bampath, bamname):
    frames = fetch_vectors(bampath)

    for x in range(global_args.bins+2):
        plt.subplot(1, global_args.bins+2, x)
        plt.plot(frames[x][0])
        plt.plot(frames[x][1])
        plt.plot(frames[x][2])

    plt.savefig(global_args.output_dir +
                "bins_coverage/bins_%s.pdf" % bamname)
    plt.close()


def runall_samples(directory):
    for filename in os.listdir(directory):
        if filename.endswith(".bam"):
            yield os.path.join(directory, filename), filename.split(".")[0]


def executable():
    pool = Pool(processes=global_args.cores)
    thread_args = []
    for bampath, bamname in runall_samples(global_args.sample_dir):
        try:
            os.mkdir(global_args.output_dir + "bins_coverage/")
        except:
            pass
        thread_args.append((bampath, bamname))

    pool.starmap_async(plot_results, thread_args)
    pool.close()
    pool.join()


def executable_2():
    for bampath, bamname in runall_samples(global_args.sample_dir):
        try:
            os.mkdir(global_args.output_dir + "frames_coverage/")
            os.mkdir(global_args.output_dir + "frames_coverage_term/")
        except:
            pass

        plot_results(bampath, bamname)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample_dir", required=True)
    parser.add_argument("--annotation_file", required=True)
    parser.add_argument("--offset", type=int, default=48)
    parser.add_argument("--cores", type=int, default=2)
    parser.add_argument("--output_dir", required=True)
    parser.add_argument("--gene_set")
    parser.add_argument("--normalize", type=bool, default=False)
    parser.add_argument("--cutoff", type=int, default=10)
    parser.add_argument("--bins", dtype=int, default=10)
    global_args = parser.parse_args()

    if global_args.cores == 1:
        executable_2()
    else:
        executable()