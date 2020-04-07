import os
import sys
import random
from collections import OrderedDict
from skimage import io
from PIL import Image, ImageOps
from pathlib import Path
import numpy as np
import itertools


class Colony:
    N = [-1, 0]
    NE = [-1, 1]
    E = [0, 1]
    SE = [1, 1]
    S = [1, 0]
    SW = [1, -1]
    W = [0, -1]
    NW = [-1, -1]
    directions = [N, NE, E, SE, S, SW, W, NW]

    class Ant:
        def __init__(self, row: int, col: int, colony: "Colony", special=False) -> None:
            """Each ant is given an initial position and the colony it belongs to"""
            self.row = row
            self.col = col
            self.colony = colony
            self.pos_memory = OrderedDict()
            self.special = special

        def __str__(self) -> str:
            """Nicely format an ant to print out"""
            return "[" + str(self.row) + ", " + str(self.col) + "]"

        def max(self, probabilities_to_pos: dict):
            keys = list(probabilities_to_pos.keys())
            keys.sort(reverse=True)
            for key in keys:
                if probabilities_to_pos[key] not in self.pos_memory:
                    return probabilities_to_pos[key]
            return None

        def index_probability(self, index: tuple):
            """
            Takes the pheromone at an index and raises it to the alpha control
            Takes the intensity at an index and raises it to the beta control
            :return: their product
            """
            row, col = index
            return (self.colony.pheromone[row, col, -1] ** self.colony.alpha) * \
                   (self.colony.intensities[row, col] ** self.colony.beta)

        def get_index_probabilities(self):
            """
            Gets all the probabilities for pixels around the ant
            :return: numerator values for the probability equation with corresponding positions
            """
            numerators = list()
            positions = list()
            # random.shuffle(self.colony.directions)
            for d in random.sample(self.colony.directions, len(self.colony.directions)):
                x = self.row + d[0]
                y = self.col + d[1]
                if (x < 0 or x >= self.colony.pheromone.shape[0] or y < 0 or y >= self.colony.pheromone.shape[1]):
                    continue
                positions.append((x, y))
                numerator = self.index_probability((x, y))
                # positions[numerator] = pos
                numerators.append(numerator)
            return numerators, positions

        def get_max_probability_pos(self):
            """
            Finds the maximum probability from the surrounding squares that are not in memory
            :return: position of the max probability square
            """
            numerators, positions = self.get_index_probabilities()
            denominator = sum(numerators)
            probabilities = list(x / denominator for x in numerators)
            pos_dict = dict(zip(probabilities, positions))
            return self.max(probabilities_to_pos=pos_dict)

        def update_memory(self):
            self.pos_memory[(self.row, self.col)] = None
            if (len(self.pos_memory) > self.colony.ant_mem):
                self.pos_memory.popitem(last=False)

        def deposit_pheromone(self):
            """
            Deposits pheromone at location if threshold is exceeded, otherwise teleports ant elsewhere
            :return: Nothing
            """
            self.update_memory()
            pos = self.get_max_probability_pos()
            if (pos == None):
                self.row = random.randrange(self.colony.img.shape[0])
                self.col = random.randrange(self.colony.img.shape[1])
                return
            row, col = pos
            # for i, j in np.ndindex(self.colony.pheromone[:2]):
            #     self.colony.pheromone[i, j, self.colony.memory_index] = 0
            if (self.colony.intensities[row, col] >= self.colony.b):
                self.row = row
                self.col = col
                self.colony.pheromone[row, col, self.colony.memory_index] = self.colony.intensities[row, col]
            else:
                self.row = random.randrange(self.colony.img.shape[0])
                self.col = random.randrange(self.colony.img.shape[1])

    def __init__(self, img_path: str, img: np.ndarray, ant_count: int, pheromone_evaporation_constant=0.1,
                 pheromone_memory_constant=20, ant_memory_constant=100, minimum_pheromone_constant=0.0001,
                 intensity_threshold_value=0.05, alpha=1.0, beta=1.0) -> None:
        self.alpha = alpha
        self.beta = beta
        self.img_path = img_path
        self.img = img
        self.i_max = img.max()
        self.intensities = np.empty(shape=(self.img.shape[0], self.img.shape[1]))
        self.set_pixel_intensities()
        self.generate_intensities_image()
        self.ants = list()
        # M x N x m + 1 matrix, m + 1 entry contains total pheromone from other memory layers
        self.pheromone = np.zeros(shape=(img.shape[0], img.shape[1], pheromone_memory_constant + 1))
        self.m = pheromone_memory_constant
        self.ant_mem = ant_memory_constant
        self.tau_min = minimum_pheromone_constant
        # Initialize total pheromone layer to min amount
        for i, j in np.ndindex(self.pheromone.shape[:2]):
            self.pheromone[i, j, -1] = self.tau_min
        # self.pheromone.fill(self.tau_min)
        self.p = pheromone_evaporation_constant
        self.b = intensity_threshold_value
        self.memory_index = 0
        # sets ants on all distinct random pixels
        pairs = set()
        for ant in range(ant_count):
            pair = None
            while (True):
                # nonlocal pair
                pair = (random.randrange(self.img.shape[0]), random.randrange(self.img.shape[1]))
                if pair not in pairs:
                    pairs.add(pair)
                    break
            row, col = pair
            if (ant % 100 == 0):
                self.ants.append(Colony.Ant(row=row, col=col, colony=self, special=True))
            else:
                self.ants.append(Colony.Ant(row=row, col=col, colony=self))

    def __str__(self) -> str:
        ants_list = ['Selection of Ants:\n']
        # count = 0;
        for i, ant in enumerate(self.ants):
            if (ant.special == True):
                ants_list.extend(['\t', ant.__str__(), '\n'])
        ants_list.append(self.pheromone[:, :, -1].__str__())
        ants_list.append('\n')
        ants_list.append(self.pheromone[:, :, self.memory_index].__str__())
        return ''.join(ants_list)

    def pixel_intensity(self, row: int, col: int) -> float:
        """
        Caclulates the intensity/importance of a given pixel by looking at surrounding pixels
        :param row: x index for the pixel
        :param col: y index for the pixel
        :return: Normalized maximum intensity
        """
        return (1 / self.i_max) * max(
            abs(int(self.img[row - 1, col - 1]) - int(self.img[row + 1, col + 1])) if (row - 1 >= 0 and col - 1 >= 0 and row + 1 < self.img.shape[0] and col + 1 < self.img.shape[1]) else 0,
            abs(int(self.img[row - 1, col + 1]) - int(self.img[row + 1, col - 1])) if (row - 1 >= 0 and col - 1 >= 0 and row + 1 < self.img.shape[0] and col + 1 < self.img.shape[1]) else 0,
            abs(int(self.img[row    , col - 1]) - int(self.img[row    , col + 1])) if (col - 1 >= 0 and col + 1 < self.img.shape[1]) else 0,
            abs(int(self.img[row - 1, col    ]) - int(self.img[row + 1, col    ])) if (row - 1 >= 0 and row + 1 < self.img.shape[0]) else 0
        )

    def set_pixel_intensities(self):
        """
        Creates and stores all of the pixel intensities, no need to keep recomputing since the value never changes
        :return: Nothing
        """
        for i, j in np.ndindex(self.img.shape):
            self.intensities[i, j] = self.pixel_intensity(i, j)
        print("Intensity: max: " + str(self.intensities.max()) + " min: " + str(self.intensities.min()) +
              " average intensity: " + str(self.intensities.mean()))
        print(self.intensities)
        # Image.fromarray(self.intensities, 'L').show()

    def generate_intensities_image(self):
        """
        Creates and stores the intensities matrix as a normal gray-scale image
        :return: Nothing
        """
        base_dir = os.path.dirname(self.img_path)
        intensities_path = os.path.join(base_dir, "Intensities")

        # Path.mkdir(intensities_path, parents=True, exist_ok=True)

        base = os.path.basename(self.img_path)
        # adjusted_path = os.path.join(os.path.dirname(self.img_path), "intensities_", base)
        final_path = os.path.join(intensities_path, base)
        arr = self.convert_to_gray(self.intensities)
        generate_image_from_array(path=final_path, array=arr)
        # Image.fromarray(self.intensities, 'L').save(final_path)

    def adjust_pheromone(self): # (self, row, column):
        """
        Globally adjusts the pheromone levels based off the sums of the memory layers and the old pheromone levels
        :return: Nothing
        """
        if (self.memory_index >= self.m - 1):
            self.memory_index = 0
        else:
            self.memory_index += 1
        for i, j in np.ndindex(self.pheromone.shape[:2]):
            # print(ij, self.pheromone[ij][!=20])
            deltas = self.pheromone[i, j, :-1]  # The memory layers
            # print(stack)
            self.pheromone[i, j, -1] = max((1 - self.p) * self.pheromone[i, j, -1] + sum(deltas), self.tau_min)
            self.pheromone[i, j, self.memory_index] = 0

    # @staticmethod
    def convert_to_gray(self, arr):
        """
        Converts a given 2d ndarray to gray-scaling
        :param arr: 2d ndarray
        :return: arr
        """
        arr = arr.copy()
        old_max = arr.max()
        old_min = arr.min()
        for i, j in np.ndindex(arr.shape):
            arr[i, j] = (((255 - 0) * (arr[i, j] - old_min)) / (old_max - old_min)) + 0
        return arr

    def generate_pheromone_image(self, iteration):
        """
        Generates the current pheromone layer with the given iteration number for the name
        :param iteration: integer - goes with naming the file
        :return: Nothing
        """
        base_dir = os.path.dirname(self.img_path)
        base = os.path.basename(self.img_path)
        fname = base.split('.')[0]

        iterations_path = os.path.join(base_dir, "Iterations", fname)

        final_path = os.path.join(iterations_path, str(iteration) + "_" + base)
        arr = self.convert_to_gray(self.pheromone[:, :, -1])
        # old_max = arr.max()
        # old_min = arr.min()
        # for i, j in np.ndindex(arr.shape):
        #     arr[i, j] = ((255 * (arr[i, j] - old_min)) / (old_max - old_min))
        generate_image_from_array(path=final_path, array=arr)

    def clean_up(self, dir_path):
        """
        Clears the directory dir_path
        :param dir_path: directory to clear
        :return: Nothing
        """
        print("cleaning " + dir_path + " ...")
        entries = None
        try:
            entries = os.listdir(path=dir_path)
        except FileNotFoundError as FNFE:
            print(type(FNFE).__name__ + ": " + argv[0] + ": " + str(FNFE), file=sys.stderr)
            return
        for entry in entries:
            path = os.path.join(dir_path, entry)
            try:
                os.remove(path=path)
            except FileNotFoundError:
                break
        print("Done cleaning!")

    def iterate(self, iterations):
        """
        Performs iterations number of iterations of the ACO algorithm
        :param iterations: number of iterations to perform
        :return: Nothing
        """
        for i in range(iterations):
            if ((i + 1) % 10 == 0):
                print("Iteration: " + str(i + 1))
                self.generate_pheromone_image(iteration=(i + 1))
            for ant in self.ants:
                ant.deposit_pheromone()
            if ((i + 1) % 10 == 0):
                print(self)
            self.adjust_pheromone()
        print("Max: " + str(self.pheromone[:, :, -1].max()))
        print(self.pheromone[:, :, -1])
        print(self.convert_to_gray(self.pheromone[:, :, -1]))


def generate_image_from_array (path, array):
    """
    Inverts the array scheme and physically saves it
    :param path: directory to store
    :param array: 2d ndarray of data
    :return: Nothing
    """
    dir_base = os.path.dirname(path)
    Path(dir_base).mkdir(parents=True, exist_ok=True)
    img = Image.fromarray(array, 'L')
    inverted_img = ImageOps.invert(img)
    inverted_img.save(path)


if __name__ == "__main__":
    argv = sys.argv
    print("Args: " + str(argv))
    if (len(argv) != 2):
        print("Usage: " + argv[0] + ": `" + os.path.basename(argv[0]) + " <image directory>'", file=sys.stderr)
        exit(1)

    entries = None
    try:
        entries = os.listdir(path=argv[1])
    except FileNotFoundError as FNFE:
        print(type(FNFE).__name__ + ": " + argv[0] + ": " + str(FNFE), file=sys.stderr)
        exit(2)

    print("Directory [" + argv[1] + "]: " + str(entries))

    for item in entries:
        if (item == "Intensities" or item == "Iterations"):
            continue
        path = os.path.join(argv[1], item)
        try:
            img = io.imread(path)
            print("Read in: `" + path + "'")
        except ValueError as VE:
            print(type(VE).__name__ + ": " + argv[0] + ": `" + path + "' is not a valid image", file=sys.stderr)
            continue
        print("[" + item + "] size: " + str(img.shape) + " len: " + str(img.shape[0] * img.shape[1]))
        print(img)
        print(img.max())
        c = Colony(img_path=path, img=img, ant_count=750, pheromone_evaporation_constant=0.04,
                   pheromone_memory_constant=30, ant_memory_constant=30, intensity_threshold_value=0.08, alpha=1.5,
                   beta=1.0)
        clean_path = os.path.join(argv[1], "Iterations", item.split('.')[0])
        c.clean_up(dir_path=clean_path)
        c.iterate(1000)
        # c.adjust_pheromone()
