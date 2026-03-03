import discord
from discord.ext import commands
from discord.ui import View, Button, Select, Modal, TextInput
import datetime
import asyncio
import os
from typing import Optional

# Настройки бота
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.moderation = True
intents.guilds = True

bot = commands.Bot(command_prefix='!', intents=intents)

# ID из вашего сервера
TICKET_PANEL_CHANNEL_ID = 1477835412012793856
TICKET_CATEGORY_ID = 1477835280315842792
GUILD_ID = 1477729837597720604
PUNISHMENT_CHANNEL_ID = 1477829936516694156

# Роли персонала
STAFF_ROLES = [
    1477825566408310974,
    1477828939551473786,
    1477827609927745677, 
    1477827889557672106,  
    1477729837597720607,
    1477828744390512711,
    1478170909436022924,
]

# Иерархия модераторов (от меньшего к большему)
MOD_ROLES_HIERARCHY = [
    1477827889557672106,  # Младший модератор
    1477828744390512711,  # Модератор
    1477729837597720607,  # Старший модератор
    1477828939551473786,  # Администратор
    1478170909436022924,  # Гл. администратор
]

# Для обратной совместимости
MOD_ROLES = MOD_ROLES_HIERARCHY

# Роль при принятии заявки
APPLICANT_ROLE_ID = 1477845619874856991

# Роли для приема заявок
APPLICATION_MANAGER_ROLES = [
    1477729837597720607,
    1477828744390512711,
]

# Канал для логов
LOG_CHANNEL_ID = None

# Хранилище активных тикетов
active_tickets = {}

# Хранилище наказаний
punishments_db = {}

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def get_guild():
    """Получить сервер"""
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        # Если сервер не найден по ID, берем первый доступный
        for g in bot.guilds:
            guild = g
            break
    return guild

async def get_member(user_id: int):
    """Получить участника по ID"""
    guild = get_guild()
    if not guild:
        return None
    return guild.get_member(user_id)

def get_mod_level(member: discord.Member) -> int:
    """Получить уровень модератора (чем меньше число, тем выше роль)"""
    for level, role_id in enumerate(MOD_ROLES_HIERARCHY):
        if member.get_role(role_id):
            return level
    return len(MOD_ROLES_HIERARCHY)  # Максимальное значение - не модератор

async def check_mod_dm(user_id: int) -> tuple:
    """Проверка прав модератора через ЛС"""
    member = await get_member(user_id)
    if not member:
        return False, "Вы не найдены на сервере"
    
    user_roles = [role.id for role in member.roles]
    
    for role_id in MOD_ROLES:
        if role_id in user_roles:
            role = member.guild.get_role(role_id)
            return True, f"Роль {role.name if role else 'модератора'} найдена"
    
    return False, "У вас нет роли модератора"

def has_mod_role(user):
    """Проверка наличия модераторской роли"""
    if not user:
        return False
    
    if isinstance(user, discord.Interaction):
        user = user.user
    
    if not hasattr(user, 'guild') or not user.guild:
        return False
    
    for role_id in MOD_ROLES:
        if user.get_role(role_id):
            return True
    return False

def can_punish(moderator: discord.Member, target: discord.Member) -> tuple:
    """Проверка, может ли модератор наказать цель"""
    
    # Проверка на самого себя
    if moderator.id == target.id:
        return False, "❌ Нельзя наказать самого себя"
    
    # Проверка на бота
    if target == bot.user:
        return False, "❌ Нельзя наказать бота"
    
    # Проверка на владельца сервера
    if target == moderator.guild.owner:
        return False, "❌ Нельзя наказать владельца сервера"
    
    # Получаем уровни модераторов
    mod_level = get_mod_level(moderator)
    target_level = get_mod_level(target)
    
    # Если цель не модератор, то наказывать можно
    if target_level >= len(MOD_ROLES_HIERARCHY):
        return True, "Можно наказать"
    
    # Если цель - модератор, проверяем иерархию
    if mod_level < target_level:  # У модератора уровень меньше = роль выше
        return True, "Можно наказать (модератор ниже рангом)"
    elif mod_level == target_level:
        return False, "❌ Нельзя наказать модератора с таким же рангом"
    else:
        return False, "❌ Нельзя наказать вышестоящего модератора"

# ========== КОМАНДА !text ==========
@bot.command()
async def text(ctx, *, message: str = None):
    """Отправить текст от имени бота и удалить команду"""
    if not has_mod_role(ctx.author):
        await ctx.send("❌ У вас нет прав модератора!")
        return
    
    if not message:
        await ctx.send("❌ Укажите текст: `!text Привет всем!`")
        return
    
    await ctx.send(message)
    await ctx.message.delete()

# ========== СИСТЕМА МЕНЮ В ЛС ==========
class ModMainMenu(View):
    """Главное меню модератора"""
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="👥 Список пользователей", style=discord.ButtonStyle.primary, emoji="📋", custom_id="menu_user_list")
    async def user_list(self, interaction: discord.Interaction, button: Button):
        has_perm, message = await check_mod_dm(interaction.user.id)
        if not has_perm:
            await interaction.response.send_message(f"❌ {message}", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        await show_user_list(interaction)
    
    @discord.ui.button(label="🔨 Выдать бан", style=discord.ButtonStyle.danger, emoji="🔨", custom_id="menu_ban")
    async def ban_menu(self, interaction: discord.Interaction, button: Button):
        has_perm, message = await check_mod_dm(interaction.user.id)
        if not has_perm:
            await interaction.response.send_message(f"❌ {message}", ephemeral=True)
            return
        
        await show_punishment_menu(interaction, "ban")
    
    @discord.ui.button(label="🔇 Выдать мут", style=discord.ButtonStyle.secondary, emoji="🔇", custom_id="menu_mute")
    async def mute_menu(self, interaction: discord.Interaction, button: Button):
        has_perm, message = await check_mod_dm(interaction.user.id)
        if not has_perm:
            await interaction.response.send_message(f"❌ {message}", ephemeral=True)
            return
        
        await show_punishment_menu(interaction, "mute")
    
    @discord.ui.button(label="⚠️ Выдать варн", style=discord.ButtonStyle.success, emoji="⚠️", custom_id="menu_warn")
    async def warn_menu(self, interaction: discord.Interaction, button: Button):
        has_perm, message = await check_mod_dm(interaction.user.id)
        if not has_perm:
            await interaction.response.send_message(f"❌ {message}", ephemeral=True)
            return
        
        await show_punishment_menu(interaction, "warn")

async def show_user_list(interaction: discord.Interaction):
    """Показать список пользователей"""
    guild = get_guild()
    if not guild:
        await interaction.followup.send("❌ Сервер не найден!", ephemeral=True)
        return
    
    members = guild.members
    online = [m for m in members if m.status != discord.Status.offline]
    offline = [m for m in members if m.status == discord.Status.offline]
    
    embed = discord.Embed(
        title="👥 Список пользователей сервера",
        color=discord.Color.blue(),
        timestamp=datetime.datetime.now()
    )
    
    embed.add_field(name="🟢 Онлайн", value=str(len(online)), inline=True)
    embed.add_field(name="🔴 Оффлайн", value=str(len(offline)), inline=True)
    embed.add_field(name="👥 Всего", value=str(len(members)), inline=True)
    
    view = View(timeout=300)
    
    async def ban_callback(btn_interaction):
        await show_punishment_menu(btn_interaction, "ban")
    
    async def mute_callback(btn_interaction):
        await show_punishment_menu(btn_interaction, "mute")
    
    async def warn_callback(btn_interaction):
        await show_punishment_menu(btn_interaction, "warn")
    
    ban_btn = Button(label="🔨 Бан", style=discord.ButtonStyle.danger, custom_id="list_ban")
    mute_btn = Button(label="🔇 Мут", style=discord.ButtonStyle.secondary, custom_id="list_mute")
    warn_btn = Button(label="⚠️ Варн", style=discord.ButtonStyle.success, custom_id="list_warn")
    
    ban_btn.callback = ban_callback
    mute_btn.callback = mute_callback
    warn_btn.callback = warn_callback
    
    view.add_item(ban_btn)
    view.add_item(mute_btn)
    view.add_item(warn_btn)
    
    await interaction.followup.send(embed=embed, view=view, ephemeral=True)

class UserSelectMenu(Select):
    """Выпадающий список пользователей"""
    def __init__(self, users, action: str, moderator: discord.Member):
        self.action = action
        self.moderator = moderator
        options = []
        
        for user in users[:25]:
            # Проверяем можно ли наказать этого пользователя
            can_punish, _ = can_punish(moderator, user)
            
            status_emoji = "🟢" if user.status == discord.Status.online else "🟡" if user.status == discord.Status.idle else "🔴"
            role_name = user.top_role.name if user.top_role and user.top_role.name != "@everyone" else "Нет роли"
            
            # Добавляем эмодзи замка если нельзя наказать
            lock_emoji = "🔒 " if not can_punish else ""
            
            options.append(
                discord.SelectOption(
                    label=f"{lock_emoji}{user.name}",
                    value=str(user.id),
                    description=f"{status_emoji} {role_name}",
                    emoji="👤"
                )
            )
        
        super().__init__(
            placeholder="Выберите пользователя...",
            min_values=1,
            max_values=1,
            options=options
        )
    
    async def callback(self, interaction: discord.Interaction):
        user_id = int(self.values[0])
        guild = get_guild()
        member = guild.get_member(user_id)
        
        if not member:
            await interaction.response.send_message("❌ Пользователь не найден на сервере!", ephemeral=True)
            return
        
        # Проверяем можно ли наказать
        can_punish, message = can_punish(self.moderator, member)
        if not can_punish:
            await interaction.response.send_message(f"❌ {message}", ephemeral=True)
            return
        
        if self.action == "ban":
            await show_ban_modal(interaction, member)
        elif self.action == "mute":
            await show_mute_modal(interaction, member)
        elif self.action == "warn":
            await show_warn_modal(interaction, member)

async def show_punishment_menu(interaction: discord.Interaction, action: str):
    """Показать меню выбора пользователя"""
    guild = get_guild()
    if not guild:
        await interaction.response.send_message("❌ Сервер не найден!", ephemeral=True)
        return
    
    moderator = guild.get_member(interaction.user.id)
    if not moderator:
        await interaction.response.send_message("❌ Модератор не найден на сервере!", ephemeral=True)
        return
    
    users = [m for m in guild.members if m.status != discord.Status.offline][:25]
    
    embed = discord.Embed(
        title=f"Выберите пользователя для {'бана' if action == 'ban' else 'мута' if action == 'mute' else 'варна'}",
        description=f"Всего онлайн: {len(users)}\n🔒 - нельзя наказать (выше рангом)",
        color=discord.Color.blue()
    )
    
    view = View(timeout=300)
    view.add_item(UserSelectMenu(users, action, moderator))
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class PunishmentModal(Modal):
    """Модальное окно для наказания"""
    def __init__(self, member: discord.Member, action: str):
        self.member = member
        self.action = action
        
        titles = {
            "mute": f"🔇 Мут для {member.name}",
            "ban": f"🔨 Бан для {member.name}",
            "warn": f"⚠️ Варн для {member.name}"
        }
        
        super().__init__(title=titles.get(action, "Наказание"))
        
        self.add_item(TextInput(
            label="Причина",
            placeholder="Введите причину наказания...",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=500
        ))
        
        if action == "mute":
            self.add_item(TextInput(
                label="Длительность",
                placeholder="10m - 10 минут, 1h - 1 час, 1d - 1 день",
                required=True,
                max_length=10
            ))
    
    async def on_submit(self, interaction: discord.Interaction):
        reason = self.children[0].value
        
        if self.action == "mute":
            duration = self.children[1].value
            await execute_mute(interaction, self.member, duration, reason)
        elif self.action == "ban":
            await execute_ban(interaction, self.member, reason)
        else:
            await execute_warn(interaction, self.member, reason)

async def show_ban_modal(interaction: discord.Interaction, member: discord.Member):
    modal = PunishmentModal(member, "ban")
    await interaction.response.send_modal(modal)

async def show_mute_modal(interaction: discord.Interaction, member: discord.Member):
    modal = PunishmentModal(member, "mute")
    await interaction.response.send_modal(modal)

async def show_warn_modal(interaction: discord.Interaction, member: discord.Member):
    modal = PunishmentModal(member, "warn")
    await interaction.response.send_modal(modal)

# ========== ИСПОЛНЕНИЕ НАКАЗАНИЙ ==========
async def execute_mute(interaction: discord.Interaction, member: discord.Member, duration: str, reason: str):
    """Выполнить мут"""
    guild = get_guild()
    moderator = guild.get_member(interaction.user.id)
    
    # Проверка иерархии
    can_punish, msg = can_punish(moderator, member)
    if not can_punish:
        await interaction.response.send_message(f"❌ {msg}", ephemeral=True)
        return
    
    time_multipliers = {"m": 60, "h": 3600, "d": 86400}
    unit = duration[-1]
    
    if unit not in time_multipliers:
        await interaction.response.send_message("❌ Неверный формат. Используйте: 10m, 1h, 1d", ephemeral=True)
        return
    
    try:
        time_value = int(duration[:-1])
        seconds = time_value * time_multipliers[unit]
    except:
        await interaction.response.send_message("❌ Неверный формат числа", ephemeral=True)
        return
    
    try:
        bot_member = guild.me
        
        if not bot_member.guild_permissions.moderate_members:
            await interaction.response.send_message("❌ У бота нет прав на мут!", ephemeral=True)
            return
        
        timeout_until = discord.utils.utcnow() + datetime.timedelta(seconds=seconds)
        await member.timeout(timeout_until, reason=reason)
        
        # Увеличиваем счетчик варнов
        punishments_db[f"warns_{member.id}"] = punishments_db.get(f"warns_{member.id}", 0) + 1
        
        # Отправляем в канал наказаний
        punishment_channel = guild.get_channel(PUNISHMENT_CHANNEL_ID)
        if punishment_channel:
            embed = discord.Embed(
                title="🔇 MUTE",
                color=discord.Color.orange(),
                timestamp=datetime.datetime.now()
            )
            embed.add_field(name="👤 Нарушитель", value=f"{member.mention} ({member.name})", inline=False)
            embed.add_field(name="🛡️ Модератор", value=f"{interaction.user.mention}", inline=False)
            embed.add_field(name="📝 Причина", value=reason, inline=False)
            embed.add_field(name="⏰ Срок", value=duration, inline=True)
            await punishment_channel.send(embed=embed)
        
        # Отправляем в ЛС нарушителю
        try:
            user_embed = discord.Embed(
                title="🔇 Вы получили мут",
                color=discord.Color.orange(),
                timestamp=datetime.datetime.now()
            )
            user_embed.add_field(name="📝 Причина", value=reason, inline=False)
            user_embed.add_field(name="⏰ Срок", value=duration, inline=True)
            user_embed.add_field(name="🛡️ Модератор", value=interaction.user.name, inline=False)
            await member.send(embed=user_embed)
        except:
            pass
        
        await interaction.response.send_message(f"✅ Мут выдан {member.mention}", ephemeral=True)
        
    except discord.Forbidden:
        await interaction.response.send_message(f"❌ У бота нет прав для мута {member.mention}", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Ошибка: {str(e)}", ephemeral=True)

async def execute_ban(interaction: discord.Interaction, member: discord.Member, reason: str):
    """Выполнить бан"""
    guild = get_guild()
    moderator = guild.get_member(interaction.user.id)
    
    # Проверка иерархии
    can_punish, msg = can_punish(moderator, member)
    if not can_punish:
        await interaction.response.send_message(f"❌ {msg}", ephemeral=True)
        return
    
    try:
        bot_member = guild.me
        
        if not bot_member.guild_permissions.ban_members:
            await interaction.response.send_message("❌ У бота нет прав на бан!", ephemeral=True)
            return
        
        await member.ban(reason=reason)
        
        punishment_channel = guild.get_channel(PUNISHMENT_CHANNEL_ID)
        if punishment_channel:
            embed = discord.Embed(
                title="🔨 BAN",
                color=discord.Color.dark_red(),
                timestamp=datetime.datetime.now()
            )
            embed.add_field(name="👤 Нарушитель", value=f"{member.mention} ({member.name})", inline=False)
            embed.add_field(name="🛡️ Модератор", value=f"{interaction.user.mention}", inline=False)
            embed.add_field(name="📝 Причина", value=reason, inline=False)
            await punishment_channel.send(embed=embed)
        
        await interaction.response.send_message(f"✅ Бан выдан {member.mention}", ephemeral=True)
        
    except discord.Forbidden:
        await interaction.response.send_message(f"❌ У бота нет прав для бана {member.mention}", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Ошибка: {str(e)}", ephemeral=True)

async def execute_warn(interaction: discord.Interaction, member: discord.Member, reason: str):
    """Выдать варн"""
    guild = get_guild()
    moderator = guild.get_member(interaction.user.id)
    
    # Проверка иерархии
    can_punish, msg = can_punish(moderator, member)
    if not can_punish:
        await interaction.response.send_message(f"❌ {msg}", ephemeral=True)
        return
    
    try:
        punishments_db[f"warns_{member.id}"] = punishments_db.get(f"warns_{member.id}", 0) + 1
        warn_count = punishments_db[f"warns_{member.id}"]
        
        punishment_channel = guild.get_channel(PUNISHMENT_CHANNEL_ID)
        if punishment_channel:
            embed = discord.Embed(
                title="⚠️ WARN",
                color=discord.Color.yellow(),
                timestamp=datetime.datetime.now()
            )
            embed.add_field(name="👤 Нарушитель", value=f"{member.mention} ({member.name})", inline=False)
            embed.add_field(name="🛡️ Модератор", value=f"{interaction.user.mention}", inline=False)
            embed.add_field(name="📝 Причина", value=reason, inline=False)
            embed.add_field(name="📊 Всего варнов", value=f"{warn_count}", inline=True)
            await punishment_channel.send(embed=embed)
        
        try:
            user_embed = discord.Embed(
                title="⚠️ Вы получили предупреждение",
                color=discord.Color.yellow(),
                timestamp=datetime.datetime.now()
            )
            user_embed.add_field(name="📝 Причина", value=reason, inline=False)
            user_embed.add_field(name="📊 Всего варнов", value=f"{warn_count}", inline=True)
            user_embed.add_field(name="🛡️ Модератор", value=interaction.user.name, inline=False)
            await member.send(embed=user_embed)
        except:
            pass
        
        await interaction.response.send_message(f"✅ Варн выдан {member.mention}", ephemeral=True)
        
    except Exception as e:
        await interaction.response.send_message(f"❌ Ошибка: {str(e)}", ephemeral=True)

# ========== КОМАНДА !menum ==========
@bot.command()
async def menum(ctx):
    """Открыть меню модератора (работает в ЛС и на сервере)"""
    # Проверяем права
    if ctx.guild:
        if not has_mod_role(ctx.author):
            await ctx.send("❌ У вас нет прав модератора!")
            return
        
        embed = discord.Embed(
            title="🛡️ Меню модератора",
            description="Меню отправлено в личные сообщения!",
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed)
    else:
        has_perm, message = await check_mod_dm(ctx.author.id)
        if not has_perm:
            await ctx.send(f"❌ {message}")
            return
    
    # Отправляем меню в ЛС
    embed = discord.Embed(
        title="🛡️ Меню модератора",
        description="Выберите действие:",
        color=discord.Color.blue()
    )
    
    try:
        await ctx.author.send(embed=embed, view=ModMainMenu())
    except Exception as e:
        if not ctx.guild:
            await ctx.send("❌ Не удалось открыть меню")

# ========== КОМАНДЫ МОДЕРАЦИИ ==========
@bot.command()
async def mute(ctx, member: discord.Member = None, duration: str = None, *, reason: str = None):
    """Выдать мут участнику"""
    if not has_mod_role(ctx.author):
        await ctx.send("❌ У вас нет прав модератора!")
        return
    
    if not member or not duration or not reason:
        embed = discord.Embed(
            title="🔇 Как использовать mute",
            description="Правильный формат: `!mute @user 10m причина`",
            color=discord.Color.orange()
        )
        embed.add_field(name="Пример", value="`!mute @user 10m Спам в чате`", inline=False)
        embed.add_field(name="Длительность", value="`10m` - 10 минут\n`1h` - 1 час\n`1d` - 1 день", inline=False)
        await ctx.send(embed=embed)
        return
    
    # Проверка иерархии
    can_punish, msg = can_punish(ctx.author, member)
    if not can_punish:
        await ctx.send(f"❌ {msg}")
        return
    
    guild = ctx.guild
    bot_member = guild.me
    
    if not bot_member.guild_permissions.moderate_members:
        await ctx.send("❌ У бота нет прав на мут!")
        return
    
    # Конвертация времени
    time_multipliers = {"m": 60, "h": 3600, "d": 86400}
    unit = duration[-1]
    
    if unit not in time_multipliers:
        await ctx.send("❌ Неверный формат. Используйте: 10m, 1h, 1d")
        return
    
    try:
        time_value = int(duration[:-1])
        seconds = time_value * time_multipliers[unit]
    except:
        await ctx.send("❌ Неверный формат числа")
        return
    
    try:
        timeout_until = discord.utils.utcnow() + datetime.timedelta(seconds=seconds)
        await member.timeout(timeout_until, reason=reason)
        
        # Увеличиваем счетчик варнов
        punishments_db[f"warns_{member.id}"] = punishments_db.get(f"warns_{member.id}", 0) + 1
        
        # Отправляем в канал наказаний
        punishment_channel = guild.get_channel(PUNISHMENT_CHANNEL_ID)
        if punishment_channel:
            embed = discord.Embed(
                title="🔇 MUTE",
                color=discord.Color.orange(),
                timestamp=datetime.datetime.now()
            )
            embed.add_field(name="👤 Нарушитель", value=f"{member.mention} ({member.name})", inline=False)
            embed.add_field(name="🛡️ Модератор", value=f"{ctx.author.mention}", inline=False)
            embed.add_field(name="📝 Причина", value=reason, inline=False)
            embed.add_field(name="⏰ Срок", value=duration, inline=True)
            await punishment_channel.send(embed=embed)
        
        # Отправляем в ЛС нарушителю
        try:
            user_embed = discord.Embed(
                title="🔇 Вы получили мут",
                color=discord.Color.orange(),
                timestamp=datetime.datetime.now()
            )
            user_embed.add_field(name="📝 Причина", value=reason, inline=False)
            user_embed.add_field(name="⏰ Срок", value=duration, inline=True)
            user_embed.add_field(name="🛡️ Модератор", value=ctx.author.name, inline=False)
            await member.send(embed=user_embed)
        except:
            pass
        
        await ctx.send(f"✅ {member.mention} получил мут на {duration} по причине: {reason}")
        
    except Exception as e:
        await ctx.send(f"❌ Ошибка: {str(e)}")

@bot.command()
async def ban(ctx, member: discord.Member = None, *, reason: str = None):
    """Забанить участника"""
    if not has_mod_role(ctx.author):
        await ctx.send("❌ У вас нет прав модератора!")
        return
    
    if not member or not reason:
        embed = discord.Embed(
            title="🔨 Как использовать ban",
            description="Правильный формат: `!ban @user причина`",
            color=discord.Color.red()
        )
        embed.add_field(name="Пример", value="`!ban @user Оскорбления`", inline=False)
        await ctx.send(embed=embed)
        return
    
    # Проверка иерархии
    can_punish, msg = can_punish(ctx.author, member)
    if not can_punish:
        await ctx.send(f"❌ {msg}")
        return
    
    guild = ctx.guild
    bot_member = guild.me
    
    if not bot_member.guild_permissions.ban_members:
        await ctx.send("❌ У бота нет прав на бан!")
        return
    
    try:
        await member.ban(reason=reason)
        
        punishment_channel = guild.get_channel(PUNISHMENT_CHANNEL_ID)
        if punishment_channel:
            embed = discord.Embed(
                title="🔨 BAN",
                color=discord.Color.dark_red(),
                timestamp=datetime.datetime.now()
            )
            embed.add_field(name="👤 Нарушитель", value=f"{member.mention} ({member.name})", inline=False)
            embed.add_field(name="🛡️ Модератор", value=f"{ctx.author.mention}", inline=False)
            embed.add_field(name="📝 Причина", value=reason, inline=False)
            await punishment_channel.send(embed=embed)
        
        await ctx.send(f"✅ {member.mention} забанен по причине: {reason}")
        
    except Exception as e:
        await ctx.send(f"❌ Ошибка: {str(e)}")

@bot.command()
async def warn(ctx, member: discord.Member = None, *, reason: str = None):
    """Выдать предупреждение"""
    if not has_mod_role(ctx.author):
        await ctx.send("❌ У вас нет прав модератора!")
        return
    
    if not member or not reason:
        embed = discord.Embed(
            title="⚠️ Как использовать warn",
            description="Правильный формат: `!warn @user причина`",
            color=discord.Color.yellow()
        )
        embed.add_field(name="Пример", value="`!warn @user Нарушение правил`", inline=False)
        await ctx.send(embed=embed)
        return
    
    # Проверка иерархии
    can_punish, msg = can_punish(ctx.author, member)
    if not can_punish:
        await ctx.send(f"❌ {msg}")
        return
    
    guild = ctx.guild
    
    # Увеличиваем счетчик варнов
    punishments_db[f"warns_{member.id}"] = punishments_db.get(f"warns_{member.id}", 0) + 1
    warn_count = punishments_db[f"warns_{member.id}"]
    
    punishment_channel = guild.get_channel(PUNISHMENT_CHANNEL_ID)
    if punishment_channel:
        embed = discord.Embed(
            title="⚠️ WARN",
            color=discord.Color.yellow(),
            timestamp=datetime.datetime.now()
        )
        embed.add_field(name="👤 Нарушитель", value=f"{member.mention} ({member.name})", inline=False)
        embed.add_field(name="🛡️ Модератор", value=f"{ctx.author.mention}", inline=False)
        embed.add_field(name="📝 Причина", value=reason, inline=False)
        embed.add_field(name="📊 Всего варнов", value=f"{warn_count}", inline=True)
        await punishment_channel.send(embed=embed)
    
    try:
        user_embed = discord.Embed(
            title="⚠️ Вы получили предупреждение",
            color=discord.Color.yellow(),
            timestamp=datetime.datetime.now()
        )
        user_embed.add_field(name="📝 Причина", value=reason, inline=False)
        user_embed.add_field(name="📊 Всего варнов", value=f"{warn_count}", inline=True)
        user_embed.add_field(name="🛡️ Модератор", value=ctx.author.name, inline=False)
        await member.send(embed=user_embed)
    except:
        pass
    
    await ctx.send(f"⚠️ {member.mention} получил предупреждение ({warn_count}/3) по причине: {reason}")

@bot.command()
async def unmute(ctx, member: discord.Member = None, *, reason: str = "Не указана"):
    """Снять мут с участника"""
    if not has_mod_role(ctx.author):
        await ctx.send("❌ У вас нет прав модератора!")
        return
    
    if not member:
        await ctx.send("❌ Укажите пользователя: `!unmute @user причина`")
        return
    
    # Проверка иерархии (для снятия мута тоже нужны права)
    can_punish, msg = can_punish(ctx.author, member)
    if not can_punish:
        await ctx.send(f"❌ {msg}")
        return
    
    guild = ctx.guild
    bot_member = guild.me
    
    if not bot_member.guild_permissions.moderate_members:
        await ctx.send("❌ У бота нет прав на снятие мута!")
        return
    
    try:
        await member.timeout(None, reason=reason)
        
        punishment_channel = guild.get_channel(PUNISHMENT_CHANNEL_ID)
        if punishment_channel:
            embed = discord.Embed(
                title="🔊 UNMUTE",
                color=discord.Color.green(),
                timestamp=datetime.datetime.now()
            )
            embed.add_field(name="👤 Пользователь", value=f"{member.mention} ({member.name})", inline=False)
            embed.add_field(name="🛡️ Модератор", value=f"{ctx.author.mention}", inline=False)
            embed.add_field(name="📝 Причина", value=reason, inline=False)
            await punishment_channel.send(embed=embed)
        
        try:
            user_embed = discord.Embed(
                title="🔊 С вас сняли мут",
                color=discord.Color.green(),
                timestamp=datetime.datetime.now()
            )
            user_embed.add_field(name="📝 Причина", value=reason, inline=False)
            user_embed.add_field(name="🛡️ Модератор", value=ctx.author.name, inline=False)
            await member.send(embed=user_embed)
        except:
            pass
        
        await ctx.send(f"✅ С {member.mention} снят мут по причине: {reason}")
        
    except Exception as e:
        await ctx.send(f"❌ Ошибка: {str(e)}")

@bot.command()
async def check(ctx, member: discord.Member = None):
    """Проверить наказания пользователя"""
    if not has_mod_role(ctx.author):
        await ctx.send("❌ У вас нет прав модератора!")
        return
    
    if not member:
        await ctx.send("❌ Укажите пользователя: `!check @user`")
        return
    
    guild = ctx.guild
    
    embed = discord.Embed(
        title=f"📋 Информация о {member.name}",
        color=discord.Color.blue(),
        timestamp=datetime.datetime.now()
    )
    
    embed.add_field(name="👤 Пользователь", value=member.mention, inline=False)
    embed.add_field(name="📅 Зашел на сервер", value=member.joined_at.strftime("%d.%m.%Y %H:%M"), inline=True)
    embed.add_field(name="📝 Ролей", value=str(len(member.roles)-1), inline=True)
    
    # Проверка активного мута
    if member.timed_out_until:
        mute_until = member.timed_out_until
        time_left = mute_until - discord.utils.utcnow()
        hours, remainder = divmod(time_left.seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        
        embed.add_field(
            name="🔇 Активный мут", 
            value=f"До: {mute_until.strftime('%d.%m.%Y %H:%M')}\nОсталось: {hours}ч {minutes}м",
            inline=False
        )
    else:
        embed.add_field(name="🔇 Активный мут", value="Нет", inline=True)
    
    # Статистика варнов
    warn_count = punishments_db.get(f"warns_{member.id}", 0)
    embed.add_field(
        name="⚠️ Варны", 
        value=f"{warn_count}/3",
        inline=True
    )
    
    # Информация о модераторских ролях
    mod_roles = []
    for role_id in MOD_ROLES_HIERARCHY:
        if member.get_role(role_id):
            role = guild.get_role(role_id)
            mod_roles.append(role.name if role else f"Роль {role_id}")
    
    if mod_roles:
        embed.add_field(name="🛡️ Роли модератора", value=", ".join(mod_roles), inline=False)
    
    embed.add_field(name="🔨 Бан", value="Нет (участник на сервере)", inline=True)
    embed.set_footer(text=f"ID: {member.id}")
    
    # Отправляем в ЛС модератору
    try:
        await ctx.author.send(embed=embed)
        if ctx.guild:
            await ctx.send("✅ Информация отправлена в ЛС!")
    except:
        await ctx.send(embed=embed)

@bot.command()
async def logs(ctx, channel: discord.TextChannel = None):
    """Привязать канал для логов"""
    if not ctx.author.get_role(1477729837597720607):
        await ctx.send("❌ У вас нет прав для использования этой команды!")
        return
    
    global LOG_CHANNEL_ID
    
    if channel:
        LOG_CHANNEL_ID = channel.id
        await ctx.send(f"✅ Канал для логов установлен: {channel.mention}")
    else:
        LOG_CHANNEL_ID = None
        await ctx.send("❌ Логи отключены. Укажите канал: !logs #канал")

# ========== ТИКЕТЫ ==========
class TicketSelect(Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="👤 Жалоба на игроков", value="player", description="Пожаловаться на другого игрока"),
            discord.SelectOption(label="🛡️ Жалоба на модерацию", value="moder", description="Пожаловаться на действия модератора"),
            discord.SelectOption(label="🔧 Технические неполадки", value="tech", description="Проблемы с ботами, баги"),
            discord.SelectOption(label="❓ Другой вопрос", value="other", description="Все остальные вопросы")
        ]
        super().__init__(placeholder="📋 Выберите категорию обращения...", min_values=1, max_values=1, options=options)
    
    async def callback(self, interaction: discord.Interaction):
        await create_ticket(interaction, self.values[0])

class TicketPanelView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketSelect())

class TicketControlView(View):
    def __init__(self, ticket_owner_id: int):
        super().__init__(timeout=None)
        self.ticket_owner_id = ticket_owner_id
        self.is_accepted = False
        self.accepted_by = None
    
    def is_staff(self, user: discord.Member) -> bool:
        for role_id in STAFF_ROLES:
            if user.get_role(role_id):
                return True
        return False
    
    def can_close(self, user: discord.Member) -> bool:
        return (user.id == self.ticket_owner_id or self.is_staff(user) or user == bot.user)
    
    @discord.ui.button(label="✅ Принять тикет", style=discord.ButtonStyle.success, custom_id="accept_ticket")
    async def accept_ticket(self, interaction: discord.Interaction, button: Button):
        if not self.is_staff(interaction.user):
            await interaction.response.send_message("❌ Только персонал может принимать тикеты!", ephemeral=True)
            return
        
        if self.is_accepted:
            await interaction.response.send_message(f"❌ Тикет уже принят {self.accepted_by.mention}", ephemeral=True)
            return
        
        self.is_accepted = True
        self.accepted_by = interaction.user
        button.disabled = True
        await interaction.message.edit(view=self)
        
        embed = discord.Embed(
            title="✅ Тикет принят в обработку",
            description=f"Администратор {interaction.user.mention} принял тикет в обработку",
            color=discord.Color.green(),
            timestamp=datetime.datetime.now()
        )
        await interaction.channel.send(embed=embed)
        await interaction.response.send_message("✅ Вы приняли тикет в обработку", ephemeral=True)
    
    @discord.ui.button(label="🔒 Закрыть тикет", style=discord.ButtonStyle.danger, custom_id="close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: Button):
        if not self.can_close(interaction.user):
            await interaction.response.send_message("❌ У вас нет прав для закрытия тикета!", ephemeral=True)
            return
        
        await interaction.response.send_message("🔒 Тикет будет закрыт через 5 секунд...")
        await asyncio.sleep(5)
        await interaction.channel.delete()

async def create_ticket(interaction: discord.Interaction, ticket_type: str):
    try:
        guild = interaction.guild
        user = interaction.user
        category = guild.get_channel(TICKET_CATEGORY_ID)
        
        if not category:
            await interaction.response.send_message("❌ Категория для тикетов не найдена!", ephemeral=True)
            return
        
        for channel in category.channels:
            if channel.name.endswith(f"-{user.name.lower()}") and isinstance(channel, discord.TextChannel):
                await interaction.response.send_message(f"❌ У вас уже есть тикет: {channel.mention}", ephemeral=True)
                return
        
        type_names = {"player": "жалоба-игрок", "moder": "жалоба-модер", "tech": "технический", "other": "вопрос"}
        channel_name = f"{type_names.get(ticket_type, 'тикет')}-{user.name.lower()}"
        
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        
        staff_mentions = []
        for role_id in STAFF_ROLES:
            role = guild.get_role(role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
                staff_mentions.append(role.mention)
        
        channel = await guild.create_text_channel(
            name=channel_name,
            category=category,
            overwrites=overwrites,
            topic=f"Тикет от {user.name} | Тип: {ticket_type}"
        )
        
        active_tickets[channel.id] = {"user_id": user.id, "type": ticket_type}
        control_view = TicketControlView(user.id)
        
        type_desc = {
            "player": "👤 Жалоба на игроков",
            "moder": "🛡️ Жалоба на модерацию",
            "tech": "🔧 Технические неполадки",
            "other": "❓ Другой вопрос"
        }
        
        embed = discord.Embed(
            title="🎫 Новый тикет создан",
            description=f"**Здравствуйте, {user.mention}!**\n\n"
                       f"**Категория:** {type_desc.get(ticket_type, 'Неизвестно')}\n\n"
                       f"Опишите вашу проблему подробно. Наши сотрудники скоро ответят вам.\n\n"
                       f"**Доступные действия:**\n"
                       f"• **✅ Принять тикет** - только для персонала\n"
                       f"• **🔒 Закрыть тикет** - для создателя и персонала",
            color=discord.Color.blue(),
            timestamp=datetime.datetime.now()
        )
        embed.set_footer(text="Спасибо за обращение!")
        
        await channel.send(
            content=f"{user.mention} {' '.join(staff_mentions)}",
            embed=embed,
            view=control_view
        )
        
        await interaction.response.send_message(f"✅ Тикет создан: {channel.mention}", ephemeral=True)
        
    except Exception as e:
        await interaction.response.send_message(f"❌ Ошибка: {str(e)}", ephemeral=True)

# ========== ЗАЯВЛЕНИЯ ==========
class ApplicationModal(Modal):
    def __init__(self, position: str):
        super().__init__(title=f"Заявление на должность: {position}")
        self.position = position
        
        self.add_item(TextInput(label="Ваше имя", placeholder="Введите ваше имя...", required=True))
        self.add_item(TextInput(label="Ваш возраст", placeholder="Сколько вам лет?", required=True))
        self.add_item(TextInput(label="Как давно играете на сервере", placeholder="Например: 3 месяца", required=True))
        self.add_item(TextInput(label="Причина подачи заявления", placeholder="Почему хотите стать частью команды?", style=discord.TextStyle.paragraph, required=True))
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        name = self.children[0].value
        age = self.children[1].value
        playtime = self.children[2].value
        reason = self.children[3].value
        
        await send_application_to_admins(interaction, self.position, name, age, playtime, reason)
        await interaction.followup.send("✅ Ваше заявление отправлено на рассмотрение!", ephemeral=True)

class ApplicationSelect(Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="📹 Медиа-команда", value="media", description="Создание контента, видео, оформление"),
            discord.SelectOption(label="🛡️ Младший модератор", value="junior_moder", description="Помощь в модерировании чата")
        ]
        super().__init__(placeholder="Выберите должность...", min_values=1, max_values=1, options=options)
    
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ApplicationModal(self.values[0]))

class ApplicationView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ApplicationSelect())

async def send_application_to_admins(interaction: discord.Interaction, position: str, name: str, age: str, playtime: str, reason: str):
    guild = interaction.guild
    
    position_names = {
        "media": "📹 Медиа-команда",
        "junior_moder": "🛡️ Младший модератор"
    }
    
    embed = discord.Embed(
        title="📨 Новая заявка в команду",
        color=discord.Color.purple(),
        timestamp=datetime.datetime.now()
    )
    embed.add_field(name="👤 Отправитель", value=f"{interaction.user.name} ({interaction.user.id})", inline=False)
    embed.add_field(name="📋 Должность", value=position_names.get(position, position), inline=False)
    embed.add_field(name="📝 Имя", value=name, inline=True)
    embed.add_field(name="🎂 Возраст", value=age, inline=True)
    embed.add_field(name="⏰ На сервере", value=playtime, inline=True)
    embed.add_field(name="💭 Причина", value=reason, inline=False)
    embed.set_footer(text="Нажмите кнопки ниже для принятия/отказа")
    
    view = ApplicationResponseView(
        applicant_id=interaction.user.id,
        guild_id=guild.id,
        position=position,
        name=name,
        age=age,
        playtime=playtime,
        reason=reason
    )
    
    for role_id in APPLICATION_MANAGER_ROLES:
        role = guild.get_role(role_id)
        if role:
            for member in role.members:
                try:
                    await member.send(embed=embed, view=view)
                except:
                    pass

class ApplicationResponseView(View):
    def __init__(self, applicant_id: int, guild_id: int, position: str, name: str, age: str, playtime: str, reason: str):
        super().__init__(timeout=None)
        self.applicant_id = applicant_id
        self.guild_id = guild_id
        self.position = position
        self.name = name
        self.age = age
        self.playtime = playtime
        self.reason = reason
    
    async def has_permission(self, user: discord.User) -> bool:
        guild = bot.get_guild(self.guild_id)
        if not guild:
            return False
        
        member = guild.get_member(user.id)
        if not member:
            return False
        
        for role_id in APPLICATION_MANAGER_ROLES:
            if member.get_role(role_id):
                return True
        
        return False
    
    @discord.ui.button(label="✅ Принять", style=discord.ButtonStyle.success, custom_id="accept_app")
    async def accept_application(self, interaction: discord.Interaction, button: Button):
        if not await self.has_permission(interaction.user):
            await interaction.response.send_message("❌ У вас нет прав для принятия заявок!", ephemeral=True)
            return
        
        guild = bot.get_guild(self.guild_id)
        if not guild:
            await interaction.response.send_message("❌ Сервер не найден!", ephemeral=True)
            return
        
        member = guild.get_member(self.applicant_id)
        if not member:
            await interaction.response.send_message("❌ Пользователь не найден на сервере!", ephemeral=True)
            return
        
        role = guild.get_role(APPLICANT_ROLE_ID)
        if role:
            await member.add_roles(role)
            
            try:
                await member.send(f"✅ Поздравляем! Ваша заявка на должность **{self.position}** принята!")
            except:
                pass
            
            await interaction.response.send_message(f"✅ Заявка принята!", ephemeral=True)
            
            for item in self.children:
                item.disabled = True
            await interaction.message.edit(view=self)
    
    @discord.ui.button(label="❌ Отказать", style=discord.ButtonStyle.danger, custom_id="reject_app")
    async def reject_application(self, interaction: discord.Interaction, button: Button):
        if not await self.has_permission(interaction.user):
            await interaction.response.send_message("❌ У вас нет прав для отказа в заявках!", ephemeral=True)
            return
        
        try:
            member = await bot.fetch_user(self.applicant_id)
            await member.send(f"❌ К сожалению, ваша заявка на должность **{self.position}** отклонена.")
        except:
            pass
        
        await interaction.response.send_message("❌ Заявка отклонена", ephemeral=True)
        
        for item in self.children:
            item.disabled = True
        await interaction.message.edit(view=self)

# ========== АДМИН КОМАНДЫ ==========
@bot.command()
@commands.has_permissions(administrator=True)
async def setup(ctx):
    """Создание панели тикетов"""
    embed = discord.Embed(
        title="🎫 Система поддержки",
        description="Добро пожаловать в систему тикетов!\n\n"
                   "**Выберите категорию обращения:**\n"
                   "👤 **Жалоба на игроков** - нарушение правил игроками\n"
                   "🛡️ **Жалоба на модерацию** - действия модераторов\n"
                   "🔧 **Технические неполадки** - баги, проблемы с ботами\n"
                   "❓ **Другой вопрос** - все остальное\n\n"
                   "После выбора будет создан приватный канал.",
        color=discord.Color.blue()
    )
    embed.set_footer(text="Меню всегда активно - можно создавать сколько угодно тикетов")
    
    await ctx.send(embed=embed, view=TicketPanelView())
    await ctx.message.delete()

@bot.command()
@commands.has_permissions(administrator=True)
async def app(ctx):
    """Создание панели подачи заявлений"""
    embed = discord.Embed(
        title="📋 Подача заявления в команду",
        description="Хотите стать частью нашей команды?\n\n"
                   "**Доступные должности:**\n"
                   "📹 **Медиа-команда** - создание контента, видео, оформление\n"
                   "🛡️ **Младший модератор** - помощь в модерировании чата\n\n"
                   "Выберите должность ниже и заполните анкету!",
        color=discord.Color.purple()
    )
    embed.set_footer(text="Заявки рассматриваются администрацией")
    
    await ctx.send(embed=embed, view=ApplicationView())
    await ctx.message.delete()

# ========== АУДИТ ==========
@bot.event
async def on_audit_log_entry_create(entry: discord.AuditLogEntry):
    if not LOG_CHANNEL_ID:
        return
    
    guild = get_guild()
    if not guild:
        return
    
    log_channel = guild.get_channel(LOG_CHANNEL_ID)
    if not log_channel:
        return
    
    embed = discord.Embed(
        title="📋 Аудит",
        timestamp=entry.created_at,
        color=discord.Color.blue()
    )
    
    action_name = str(entry.action).split('.')[-1]
    
    embed.add_field(name="👤 Инициатор", value=f"{entry.user.mention} ({entry.user.name})", inline=False)
    
    if entry.target:
        if isinstance(entry.target, discord.Member):
            embed.add_field(name="🎯 Цель", value=f"{entry.target.mention} ({entry.target.name})", inline=False)
        elif isinstance(entry.target, discord.Role):
            embed.add_field(name="🎯 Цель", value=f"Роль: {entry.target.mention}", inline=False)
        elif isinstance(entry.target, discord.TextChannel):
            embed.add_field(name="🎯 Цель", value=f"Канал: {entry.target.mention}", inline=False)
        else:
            embed.add_field(name="🎯 Цель", value=str(entry.target), inline=False)
    
    embed.add_field(name="🔧 Действие", value=action_name, inline=False)
    
    if entry.reason:
        embed.add_field(name="📝 Причина", value=entry.reason, inline=False)
    
    await log_channel.send(embed=embed)

@bot.event
async def on_ready():
    print(f"✅ Бот {bot.user} запущен!")
    
    guild = get_guild()
    if guild:
        print(f"📁 Найден сервер: {guild.name} (ID: {guild.id})")
        print(f"👥 MOD ролей: {len(MOD_ROLES_HIERARCHY)}")
        print(f"📋 Иерархия модераторов:")
        
        for i, role_id in enumerate(MOD_ROLES_HIERARCHY):
            role = guild.get_role(role_id)
            if role:
                print(f"  {i}. {role.name} ({role_id})")
            else:
                print(f"  {i}. Роль {role_id} не найдена на сервере!")
    else:
        print(f"❌ Сервер {GUILD_ID} не найден!")
        print(f"📋 Доступные серверы:")
        for g in bot.guilds:
            print(f"  • {g.name} (ID: {g.id})")
    
    bot.add_view(TicketPanelView())
    bot.add_view(ApplicationView())
    bot.add_view(ModMainMenu())
    
    for channel_id, data in active_tickets.items():
        channel = bot.get_channel(channel_id)
        if channel:
            bot.add_view(TicketControlView(data["user_id"]))

# Запуск бота
if __name__ == "__main__":
    token = os.getenv('DISCORD_BOT_TOKEN')
    if not token:
        print("❌ Ошибка: Не найден токен бота!")
        exit(1)
    
    bot.run(token)
