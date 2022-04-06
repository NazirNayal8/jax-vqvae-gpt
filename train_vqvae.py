import pickle
import json
import argparse
from pathlib import Path
from collections import defaultdict

from tqdm import tqdm
import jax
import optax

from dataset import load_mnist
from trainers.vqvae_trainer import VqVaeTrainer
from logger import get_writer, log_dict
from annotations import VqVaeConfig


def parse_args():
    parser = argparse.ArgumentParser(
        description="Train a VQ-VAE on the MNIST dataset.")
    parser.add_argument("-f", "--file", type=str, required=True,
                        help="path to the json config file.")
    return parser.parse_args()


def main(config: VqVaeConfig):
    writer = get_writer(config.logdir)
    exp_dir = writer.logdir

    # save config file
    with open(Path(exp_dir) / "config.json", "w") as f:
        json.dump(config._asdict(), f, indent=4)

    # load dataset
    _, dset_train = load_mnist(split="train",
                               batch_size=config.train_batch_size,
                               percentage=config.train_dset_percentage,
                               seed=config.seed)
    _, dset_test = load_mnist(split="test",
                              batch_size=config.test_batch_size,
                              percentage=config.test_dset_percentage,
                              seed=config.seed)

    # initialize model
    optimizer = optax.adamw(config.learning_rate,
                            weight_decay=config.weight_decay)
    trainer = VqVaeTrainer(K=config.K,
                           D=config.D,
                           compression_level=config.compression_level,
                           res_layers=config.res_layers,
                           commitment_loss=config.commitment_loss,
                           optimizer=optimizer)
    key = jax.random.PRNGKey(config.seed)
    train_state = trainer.initial_state(key, next(dset_train)[1])

    # training loop
    for i in tqdm(range(config.train_steps)):
        # update
        epoch, batch = next(dset_train)
        train_state, logs = trainer.update(train_state, batch)

        # log
        logs["scalar_epoch"] = epoch
        log_dict(writer, logs, step=i, prefix="train/")

        # evaluate
        if (i + 1) % config.test_every == 0:
            logs = defaultdict(list)
            for _ in range(config.test_steps):
                _, batch = next(dset_test)
                log = trainer.evaluate(train_state, batch)
                for k, v in log.items():
                    logs[k].append(v)
            log_dict(writer, logs, step=i, prefix="test/")

    # save model
    with open(Path(exp_dir) / config.output_name, "wb") as f:
        pickle.dump(train_state, f)

    writer.close()


if __name__ == "__main__":
    args = parse_args()
    with open(args.file, "r") as f:
        config = VqVaeConfig(**json.load(f))

    main(config)
