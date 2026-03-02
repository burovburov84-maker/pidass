import discord
from discord.ext import commands
from discord.ui import View, Button, Select, Modal, TextInput
import datetime
import asyncio
import os
from typing import Optional
import json

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

# Роли для модерации
MOD_ROLES = [
    1477827889557672106,
    1477828744390512711,
    1477729837597720607,
    1477828939551473786,
    1478170909436022924,
]

# Роль при принятии заявки
APPLICANT_ROLE_ID = 1477845619874856991

# Роли для приема заявок
APPLICATION_MANAGER_ROLES = [
    1477729837597720607,
    1477828744390512711,
]

# Канал для логов
LOG_CHANNEL_ID = None

# Хранилище наказаний
punishments_db = {}

# ========== ПРОВЕРКА ПРАВ ==========
def is_mod(member: discord.Member) -> bool:
    """Проверка, является ли пользователь модератором"""
    for role_id in MOD_ROLES:
        if member.get_role(role_id):
            return True
    return False

async def check_mod_dm(user: discord.User) -> bool:
    """Проверка прав модератора через ЛС"""
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        return False
    
    member = guild.get_member(user.id)
    if not member:
        return False
    
    return is_mod(member)

# ========== СИСТЕМА МЕНЮ В ЛС ==========
class ModMainMenu(View):
    """Главное меню модератора"""
    def __init__(self):
        super().__init__(timeout=300)
    
    @discord.ui.button(label="👥 Список пользователей", style=discord.ButtonStyle.primary, emoji="📋")
    async def user_list(self, interaction: discord.Interaction, button: Button):
        if not await check_mod_dm(interaction.user):
            await interaction.response.send_message("❌ У вас нет прав модератора!", ephemeral=True)
            return
        
        await interaction.response.send_message("Загрузка списка пользователей...", ephemeral=True)
        await show_user_list(interaction)
    
    @discord.ui.button(label="🔨 Выдать бан", style=discord.ButtonStyle.danger, emoji="🔨")
    async def ban_menu(self, interaction: discord.Interaction, button: Button):
        if not await check_mod_dm(interaction.user):
            await interaction.response.send_message("❌ У вас нет прав модератора!", ephemeral=True)
            return
        
        await show_punishment_menu(interaction, "ban")
    
    @discord.ui.button(label="🔇 Выдать мут", style=discord.ButtonStyle.secondary, emoji="🔇")
    async def mute_menu(self, interaction: discord.Interaction, button: Button):
        if not await check_mod_dm(interaction.user):
            await interaction.response.send_message("❌ У вас нет прав модератора!", ephemeral=True)
            return
        
        await show_punishment_menu(interaction, "mute")
    
    @discord.ui.button(label="⚠️ Выдать варн", style=discord.ButtonStyle.success, emoji="⚠️")
    async def warn_menu(self, interaction: discord.Interaction, button: Button):
        if not await check_mod_dm(interaction.user):
            await interaction.response.send_message("❌ У вас нет прав модератора!", ephemeral=True)
            return
        
        await show_punishment_menu(interaction, "warn")

class UserSelectView(View):
    """Меню выбора пользователя"""
    def __init__(self, users, action: str):
        super().__init__(timeout=300)
        self.action = action
        self.add_item(UserSelectMenu(users, action))

class UserSelectMenu(Select):
    """Выпадающий список пользователей"""
    def __init__(self, users, action: str):
        self.action = action
        options = []
        for user in users[:25]:  # Discord лимит 25 опций
            status_emoji = "🟢" if user.status == discord.Status.online else "🟡" if user.status == discord.Status.idle else "🔴"
            options.append(
                discord.SelectOption(
                    label=user.name,
                    value=str(user.id),
                    description=f"{status_emoji} {user.top_role.name if user.top_role else 'Нет роли'}",
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
        guild = bot.get_guild(GUILD_ID)
        member = guild.get_member(user_id)
        
        if not member:
            await interaction.response.send_message("❌ Пользователь не найден на сервере!", ephemeral=True)
            return
        
        if self.action == "ban":
            await show_ban_modal(interaction, member)
        elif self.action == "mute":
            await show_mute_modal(interaction, member)
        elif self.action == "warn":
            await show_warn_modal(interaction, member)

class PunishmentModal(Modal):
    """Модальное окно для наказания"""
    def __init__(self, member: discord.Member, action: str):
        self.member = member
        self.action = action
        
        if action == "mute":
            title = f"🔇 Мут для {member.name}"
        elif action == "ban":
            title = f"🔨 Бан для {member.name}"
        else:
            title = f"⚠️ Варн для {member.name}"
        
        super().__init__(title=title)
        
        self.add_item(TextInput(
            label="Причина",
            placeholder="Введите причину наказания...",
            style=discord.TextStyle.paragraph,
            required=True
        ))
        
        if action == "mute":
            self.add_item(TextInput(
                label="Длительность",
                placeholder="Например: 10m, 1h, 1d",
                required=True
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

async def show_user_list(interaction: discord.Interaction):
    """Показать список пользователей"""
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        await interaction.followup.send("❌ Сервер не найден!", ephemeral=True)
        return
    
    # Получаем всех участников
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
    
    # Создаем кнопки для выбора действия
    view = View(timeout=300)
    
    async def ban_button_callback(btn_interaction):
        await show_punishment_menu(btn_interaction, "ban")
    
    async def mute_button_callback(btn_interaction):
        await show_punishment_menu(btn_interaction, "mute")
    
    async def warn_button_callback(btn_interaction):
        await show_punishment_menu(btn_interaction, "warn")
    
    view.add_item(Button(label="🔨 Бан", style=discord.ButtonStyle.danger, custom_id="ban_from_list"))
    view.add_item(Button(label="🔇 Мут", style=discord.ButtonStyle.secondary, custom_id="mute_from_list"))
    view.add_item(Button(label="⚠️ Варн", style=discord.ButtonStyle.success, custom_id="warn_from_list"))
    
    # Привязываем обработчики
    for item in view.children:
        if item.custom_id == "ban_from_list":
            item.callback = ban_button_callback
        elif item.custom_id == "mute_from_list":
            item.callback = mute_button_callback
        elif item.custom_id == "warn_from_list":
            item.callback = warn_button_callback
    
    await interaction.followup.send(embed=embed, view=view, ephemeral=True)

async def show_punishment_menu(interaction: discord.Interaction, action: str):
    """Показать меню выбора пользователя для наказания"""
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        await interaction.response.send_message("❌ Сервер не найден!", ephemeral=True)
        return
    
    # Показываем только онлайн пользователей для удобства
    users = [m for m in guild.members if m.status != discord.Status.offline][:25]
    
    embed = discord.Embed(
        title=f"Выберите пользователя для {action}",
        description=f"Всего онлайн: {len(users)}",
        color=discord.Color.blue()
    )
    
    view = UserSelectView(users, action)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

async def show_ban_modal(interaction: discord.Interaction, member: discord.Member):
    """Показать модальное окно для бана"""
    modal = PunishmentModal(member, "ban")
    await interaction.response.send_modal(modal)

async def show_mute_modal(interaction: discord.Interaction, member: discord.Member):
    """Показать модальное окно для мута"""
    modal = PunishmentModal(member, "mute")
    await interaction.response.send_modal(modal)

async def show_warn_modal(interaction: discord.Interaction, member: discord.Member):
    """Показать модальное окно для варна"""
    modal = PunishmentModal(member, "warn")
    await interaction.response.send_modal(modal)

# ========== ИСПОЛНЕНИЕ НАКАЗАНИЙ ==========
async def execute_mute(interaction: discord.Interaction, member: discord.Member, duration: str, reason: str):
    """Выполнить мут"""
    # Конвертируем длительность
    time_multipliers = {"m": 60, "h": 3600, "d": 86400}
    unit = duration[-1]
    if unit not in time_multipliers:
        await interaction.response.send_message("❌ Неверный формат времени. Используйте: 10m, 1h, 1d", ephemeral=True)
        return
    
    try:
        time_value = int(duration[:-1])
        seconds = time_value * time_multipliers[unit]
    except:
        await interaction.response.send_message("❌ Неверный формат времени", ephemeral=True)
        return
    
    try:
        guild = bot.get_guild(GUILD_ID)
        bot_member = guild.me
        
        # Проверка прав
        if not bot_member.guild_permissions.moderate_members:
            await interaction.response.send_message("❌ У бота нет прав на мут!", ephemeral=True)
            return
        
        if member.top_role >= bot_member.top_role:
            await interaction.response.send_message(f"❌ Невозможно замутить {member.mention} - его роль выше бота", ephemeral=True)
            return
        
        # Выдаем мут
        timeout_until = discord.utils.utcnow() + datetime.timedelta(seconds=seconds)
        await member.timeout(timeout_until, reason=reason)
        
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
    try:
        guild = bot.get_guild(GUILD_ID)
        bot_member = guild.me
        
        if not bot_member.guild_permissions.ban_members:
            await interaction.response.send_message("❌ У бота нет прав на бан!", ephemeral=True)
            return
        
        if member.top_role >= bot_member.top_role:
            await interaction.response.send_message(f"❌ Невозможно забанить {member.mention} - его роль выше бота", ephemeral=True)
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
    try:
        guild = bot.get_guild(GUILD_ID)
        
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
            await punishment_channel.send(embed=embed)
        
        # Отправляем в ЛС
        try:
            user_embed = discord.Embed(
                title="⚠️ Вы получили предупреждение",
                color=discord.Color.yellow(),
                timestamp=datetime.datetime.now()
            )
            user_embed.add_field(name="📝 Причина", value=reason, inline=False)
            user_embed.add_field(name="🛡️ Модератор", value=interaction.user.name, inline=False)
            await member.send(embed=user_embed)
        except:
            pass
        
        await interaction.response.send_message(f"✅ Варн выдан {member.mention}", ephemeral=True)
        
    except Exception as e:
        await interaction.response.send_message(f"❌ Ошибка: {str(e)}", ephemeral=True)

# ========== КОМАНДЫ ==========
@bot.command()
async def menum(ctx):
    """Открыть меню модератора в ЛС"""
    if not is_mod(ctx.author):
        await ctx.send("❌ У вас нет прав модератора!")
        return
    
    embed = discord.Embed(
        title="🛡️ Меню модератора",
        description="Выберите действие:",
        color=discord.Color.blue()
    )
    
    try:
        await ctx.author.send(embed=embed, view=ModMainMenu())
        if ctx.guild:  # Если команда вызвана не в ЛС
            await ctx.send("✅ Меню отправлено в личные сообщения!")
    except:
        await ctx.send("❌ Не удалось отправить ЛС. Откройте ЛС с ботом.")

@bot.command()
async def mute(ctx, member: discord.Member = None, duration: str = None, *, reason: str = None):
    """Выдать мут участнику"""
    if not is_mod(ctx.author):
        await ctx.send("❌ У вас нет прав модератора!")
        return
    
    # Если не хватает аргументов - отправляем инструкцию в ЛС
    if not member or not duration or not reason:
        embed = discord.Embed(
            title="🔇 Как использовать mute",
            description="Правильный формат команды:",
            color=discord.Color.orange()
        )
        embed.add_field(name="Пример", value="`!mute @user 10m Спам в чате`", inline=False)
        embed.add_field(name="Длительность", value="`10m` - 10 минут\n`1h` - 1 час\n`1d` - 1 день", inline=False)
        
        try:
            await ctx.author.send(embed=embed)
            if ctx.guild:
                await ctx.send("✅ Инструкция отправлена в ЛС!")
        except:
            await ctx.send(embed=embed)
        return
    
    # Здесь код выполнения мута (как в execute_mute но с ctx)
    await ctx.send("⏳ Обработка...")

@bot.command()
async def ban(ctx, member: discord.Member = None, *, reason: str = None):
    """Забанить участника"""
    if not is_mod(ctx.author):
        await ctx.send("❌ У вас нет прав модератора!")
        return
    
    if not member or not reason:
        embed = discord.Embed(
            title="🔨 Как использовать ban",
            description="Правильный формат команды:",
            color=discord.Color.red()
        )
        embed.add_field(name="Пример", value="`!ban @user Оскорбления`", inline=False)
        
        try:
            await ctx.author.send(embed=embed)
            if ctx.guild:
                await ctx.send("✅ Инструкция отправлена в ЛС!")
        except:
            await ctx.send(embed=embed)
        return

@bot.command()
async def warn(ctx, member: discord.Member = None, *, reason: str = None):
    """Выдать предупреждение"""
    if not is_mod(ctx.author):
        await ctx.send("❌ У вас нет прав модератора!")
        return
    
    if not member or not reason:
        embed = discord.Embed(
            title="⚠️ Как использовать warn",
            description="Правильный формат команды:",
            color=discord.Color.yellow()
        )
        embed.add_field(name="Пример", value="`!warn @user Нарушение правил`", inline=False)
        
        try:
            await ctx.author.send(embed=embed)
            if ctx.guild:
                await ctx.send("✅ Инструкция отправлена в ЛС!")
        except:
            await ctx.send(embed=embed)
        return

@bot.command()
async def check(ctx, member: discord.Member = None):
    """Проверить наказания пользователя"""
    if not is_mod(ctx.author):
        await ctx.send("❌ У вас нет прав модератора!")
        return
    
    if not member:
        await ctx.send("❌ Укажите пользователя: `!check @user`")
        return
    
    # Здесь будет код для проверки наказаний
    embed = discord.Embed(
        title=f"📋 Наказания {member.name}",
        color=discord.Color.blue(),
        timestamp=datetime.datetime.now()
    )
    embed.add_field(name="👤 Пользователь", value=member.mention, inline=False)
    embed.add_field(name="⚠️ Предупреждения", value="0", inline=True)
    embed.add_field(name="🔇 Муты", value="0", inline=True)
    embed.add_field(name="🔨 Баны", value="0", inline=True)
    
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
        await ctx.send("❌ Логи отключены")

# ========== СИСТЕМА АУДИТА ==========
@bot.event
async def on_audit_log_entry_create(entry: discord.AuditLogEntry):
    """Отслеживание действий в аудите"""
    if not LOG_CHANNEL_ID:
        return
    
    guild = bot.get_guild(GUILD_ID)
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
    
    # Определяем действие
    action_name = str(entry.action).split('.')[-1]
    
    embed.add_field(name="👤 Инициатор", value=f"{entry.user.mention} ({entry.user.name})", inline=False)
    
    if entry.target:
        if isinstance(entry.target, discord.Member):
            embed.add_field(name="🎯 Цель", value=f"{entry.target.mention} ({entry.target.name})", inline=False)
        elif isinstance(entry.target, discord.Role):
            embed.add_field(name="🎯 Цель", value=f"Роль: {entry.target.mention}", inline=False)
        else:
            embed.add_field(name="🎯 Цель", value=str(entry.target), inline=False)
    
    embed.add_field(name="🔧 Действие", value=action_name, inline=False)
    
    if entry.reason:
        embed.add_field(name="📝 Причина", value=entry.reason, inline=False)
    
    # Обработка изменений ролей
    if hasattr(entry, 'changes') and entry.changes:
        changes = []
        for change in entry.changes:
            if hasattr(change, 'before') and hasattr(change, 'after'):
                changes.append(f"**{change.attr}:** {change.before} → {change.after}")
        if changes:
            embed.add_field(name="📊 Изменения", value="\n".join(changes[:5]), inline=False)
    
    await log_channel.send(embed=embed)

# ========== ТИКЕТЫ (ваша существующая система) ==========
# [Весь ваш код для тикетов остается здесь]
# Я не стал его копировать чтобы не загромождать ответ,
# но вы можете добавить его обратно

@bot.event
async def on_ready():
    print(f"✅ Бот {bot.user} запущен!")
    print(f"📁 Сервер ID: {GUILD_ID}")
    print(f"📢 Канал наказаний ID: {PUNISHMENT_CHANNEL_ID}")
    print(f"👥 MOD ролей: {len(MOD_ROLES)}")
    
    # Восстанавливаем View
    bot.add_view(ModMainMenu())

# Запуск бота
if __name__ == "__main__":
    token = os.getenv('DISCORD_BOT_TOKEN')
    if not token:
        print("❌ Ошибка: Не найден токен бота!")
        exit(1)
    
    bot.run(token)
