# ------------------------------------------
# coding=utf-8
# Copyright 2023 The HuggingFace Inc. team. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ------------------------------------------
# Modification:
# -- Joohyung Park - hynciath51@gmail.com, 
# -- Sangyun Lee - 99sansan@naver.com
# ------------------------------------------
"""Fine-tuning script for Stable Diffusion for text2image with support for LoRA."""

import torch
import torch.nn as nn
import torch.nn.functional as F 

from torch.utils.data import DataLoader
from torch.optim.lr_scheduler import CosineAnnealingLR

from model import diffusion_model
from diffusers import get_cosine_schedule_with_warmup
from load_data import PokemonDataset
from torchvision import transforms
from tqdm import tqdm

def train(args):
    model = diffusion_model(args)
    device = torch.device('cuda:0') if torch.cuda.is_available() else torch.device('cpu')
    print(f'device : {device}')
    # Data loader
    train_transforms = transforms.Compose(
        [
            transforms.Resize(args.resolution, interpolation=transforms.InterpolationMode.BILINEAR),
            transforms.CenterCrop(args.resolution),
            transforms.RandomHorizontalFlip(), #if args.random_flip else transforms.Lambda(lambda x: x),
            transforms.ToTensor(),
            transforms.Normalize([0.5], [0.5]),
        ]
    )
    dataset = PokemonDataset(root_dir=args.dataset_dir, transform=train_transforms, Tokenizer= model.tokenizer) 
    train_dataloader = DataLoader(dataset, batch_size=args.batch_size, shuffle=True)
    

    model.train()
    model.unet.requires_grad_(False)
    model.vae.requires_grad_(False)
    model.text_encoder.requires_grad_(False)

    model.set_lora(args)
    
    weight_dtype = torch.float32
    model.to(device, dtype=weight_dtype)
    loss_class = nn.CrossEntropyLoss()
    optimizer = torch.optim.AdamW(
        model.lora_layers.parameters(),
        lr=args.lr,
        betas=(0.9, 0.999),
        weight_decay=1e-2,
        eps=1e-08,
    )
    scheduler = get_cosine_schedule_with_warmup(optimizer, num_warmup_steps = 0,num_training_steps = len(train_dataloader) * args.epochs)


    for epoch in range(0,args.epochs):
        model.unet.train()
        train_loss = 0.0        
        for step, batch in enumerate(tqdm(train_dataloader)):
            optimizer.zero_grad()
            pixel_values = batch["image"].to(device = device, dtype=weight_dtype)
            input_ids = batch['prompt'].to(device = device)
            model_pred, target, features_pred, logit_pred = model(pixel_values, input_ids)
            # model_pred : latent_predicted by unet
            # target : target_latent
            # feature_pred : prediction for feature
            # logit pred : class prediction
            loss_latent = F.mse_loss(model_pred.float(), target.float(), reduction="mean")
            loss_features = F.mse_loss(features_pred.float(), batch['tabular'].to(device = device), reduction="mean")
            loss_calss = loss_class(logit_pred, batch['p_type'].to(device = device))
            loss = loss_latent + loss_features + loss_calss
            loss.backward()
            optimizer.step()
        scheduler.step()
        