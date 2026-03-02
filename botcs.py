import discord
from discord.ext import commands
from discord.ui import View, Button, Select, Modal, TextInput
import datetime
import asyncio
import os

# Настройки бота
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.moderation = True

bot = commands.Bot(command_prefix='!', intents=intents)

# ID из вашего сервера
TICKET_PANEL_CHANNEL_ID = 1477835412012793856  # Канал для панели
TICKET_CATEGORY_ID = 1477835280315842792      # Категория для тикетов
GUILD_ID = 1477729837597720604  # ID вашего сервера

# КАНАЛ ДЛЯ НАКАЗАНИЙ
PUNISHMENT_CHANNEL_ID = 1477829936516694156  # Канал куда писать о наказаниях

# Роли персонала
STAFF_ROLES = [
    1477825566408310974,  # Модератор
    1477828939551473786,  # Администратор
    1477827609927745677, 
    1477827889557672106,  
    1477729837597720607,  # Роль для приема заявок
    1477828744390512711,  # Роль для приема заявок
    1478170909436022924,  # Новая роль
]

# Роли для модерации (кто может использовать команды)
MOD_ROLES = [
    1477827889557672106,  # Модератор
    1477828744390512711,  # Роль 1
    1477729837597720607,  # Роль 2
    1477828939551473786,  # Администратор
    1478170909436022924,  # Новая роль
]

# Роль при принятии заявки
APPLICANT_ROLE_ID = 1477845619874856991

# Роли для приема заявок
APPLICATION_MANAGER_ROLES = [
    1477729837597720607,
    1477828744390512711,
]

# Канал для логов
LOG_CHANNEL_ID = None  # Будет установлено через команду !logs

# Хранилище активных тикетов
active_tickets = {}

# ========== СИСТЕМА ЛОГОВ ==========
async def log_action(ctx, action: str, target: discord.Member, reason: str, duration: str = None):
    """Логирование наказаний в специальный канал"""
    global LOG_CHANNEL_ID
    
    punishment_channel = ctx.guild.get_channel(PUNISHMENT_CHANNEL_ID)
    if not punishment_channel:
        return
    
    # Определяем цвет в зависимости от действия
    colors = {
        "MUTE": discord.Color.orange(),
        "BAN": discord.Color.dark_red(),
        "WARN": discord.Color.yellow(),
        "UNMUTE": discord.Color.green()
    }
    color = colors.get(action, discord.Color.blue())
    
    # Создаем embed для канала наказаний
    embed = discord.Embed(
        title=f"{self.get_action_emoji(action)} {action}",
        color=color,
        timestamp=datetime.datetime.now()
    )
    embed.add_field(name="👤 Нарушитель", value=f"{target.mention} ({target.name})", inline=False)
    embed.add_field(name="🛡️ Модератор", value=f"{ctx.author.mention} ({ctx.author.name})", inline=False)
    embed.add_field(name="📝 Причина", value=reason, inline=False)
    
    if duration:
        embed.add_field(name="⏰ Срок", value=duration, inline=True)
    
    embed.set_footer(text=f"ID нарушителя: {target.id}")
    
    await punishment_channel.send(embed=embed)
    
    # Отправляем в ЛС нарушителю
    try:
        user_embed = discord.Embed(
            title=f"{self.get_action_emoji(action)} Вы получили {action.lower()}",
            color=color,
            timestamp=datetime.datetime.now()
        )
        user_embed.add_field(name="📝 Причина", value=reason, inline=False)
        if duration:
            user_embed.add_field(name="⏰ Срок", value=duration, inline=True)
        user_embed.add_field(name="🛡️ Модератор", value=ctx.author.name, inline=False)
        user_embed.set_footer(text=f"Сервер: {ctx.guild.name}")
        
        await target.send(embed=user_embed)
    except:
        pass  # Если нельзя отправить ЛС
    
    # Логируем в общий лог-канал если есть
    if LOG_CHANNEL_ID:
        log_channel = ctx.guild.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            log_embed = discord.Embed(
                title=f"📋 {action}",
                description=f"**Модератор:** {ctx.author.mention}\n**Нарушитель:** {target.mention}\n**Причина:** {reason}",
                color=color
            )
            await log_channel.send(embed=log_embed)

def get_action_emoji(action: str) -> str:
    """Возвращает эмодзи для действия"""
    emojis = {
        "MUTE": "🔇",
        "BAN": "🔨",
        "WARN": "⚠️",
        "UNMUTE": "🔊"
    }
    return emojis.get(action, "🔹")

# ========== КОМАНДЫ ДЛЯ МОДЕРАЦИИ ==========
def has_mod_role(ctx):
    """Проверка наличия модераторской роли"""
    for role_id in MOD_ROLES:
        if ctx.author.get_role(role_id):
            return True
    return False

@bot.command()
@commands.check(has_mod_role)
async def text(ctx, *, message: str):
    """Отправить текст от имени бота и удалить команду"""
    await ctx.send(message)
    await ctx.message.delete()
    
    # Логируем в общий лог если есть
    if LOG_CHANNEL_ID:
        log_channel = ctx.guild.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            embed = discord.Embed(
                title="💬 Текстовое сообщение",
                description=f"**Отправитель:** {ctx.author.mention}\n**Сообщение:** {message}",
                color=discord.Color.blue()
            )
            await log_channel.send(embed=embed)

@bot.command()
@commands.check(has_mod_role)
async def mute(ctx, member: discord.Member, duration: str, *, reason: str = "Не указана"):
    """Выдать мут участнику (формат: 10m, 1h, 1d)"""
    # Конвертируем длительность
    time_multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    unit = duration[-1]
    if unit not in time_multipliers:
        await ctx.send("❌ Неверный формат времени. Используйте: 10m, 1h, 1d")
        return
    
    try:
        time_value = int(duration[:-1])
        seconds = time_value * time_multipliers[unit]
    except:
        await ctx.send("❌ Неверный формат времени")
        return
    
    try:
        # Выдаем мут
        await member.timeout(discord.utils.utcnow() + datetime.timedelta(seconds=seconds), reason=reason)
        
        # Отправляем в канал где написали команду (краткое уведомление)
        await ctx.send(f"✅ {member.mention} получил мут на {duration} по причине: {reason}")
        
        # Логируем в специальный канал и ЛС
        await log_action(ctx, "MUTE", member, reason, duration)
        
    except Exception as e:
        await ctx.send(f"❌ Ошибка при выдаче мута: {str(e)}")

@bot.command()
@commands.check(has_mod_role)
async def ban(ctx, member: discord.Member, *, reason: str = "Не указана"):
    """Забанить участника"""
    try:
        await member.ban(reason=reason)
        
        # Краткое уведомление в текущий канал
        await ctx.send(f"✅ {member.mention} забанен по причине: {reason}")
        
        # Логируем в специальный канал и ЛС
        await log_action(ctx, "BAN", member, reason)
        
    except Exception as e:
        await ctx.send(f"❌ Ошибка при бане: {str(e)}")

@bot.command()
@commands.check(has_mod_role)
async def warn(ctx, member: discord.Member, *, reason: str = "Не указана"):
    """Выдать предупреждение участнику"""
    
    # Краткое уведомление в текущий канал
    await ctx.send(f"⚠️ {member.mention} получил предупреждение по причине: {reason}")
    
    # Логируем в специальный канал и ЛС
    await log_action(ctx, "WARN", member, reason)

@bot.command()
@commands.check(has_mod_role)
async def unmute(ctx, member: discord.Member, *, reason: str = "Не указана"):
    """Снять мут с участника"""
    try:
        await member.timeout(None, reason=reason)
        
        # Краткое уведомление в текущий канал
        await ctx.send(f"✅ С {member.mention} снят мут по причине: {reason}")
        
        # Логируем
        punishment_channel = ctx.guild.get_channel(PUNISHMENT_CHANNEL_ID)
        if punishment_channel:
            embed = discord.Embed(
                title="🔊 UNMUTE",
                color=discord.Color.green(),
                timestamp=datetime.datetime.now()
            )
            embed.add_field(name="👤 Пользователь", value=f"{member.mention} ({member.name})", inline=False)
            embed.add_field(name="🛡️ Модератор", value=f"{ctx.author.mention} ({ctx.author.name})", inline=False)
            embed.add_field(name="📝 Причина", value=reason, inline=False)
            await punishment_channel.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Ошибка при снятии мута: {str(e)}")

@bot.command()
async def logs(ctx, channel: discord.TextChannel = None):
    """Привязать канал для логов (только для роли 1477729837597720607)"""
    if not ctx.author.get_role(1477729837597720607):
        await ctx.send("❌ У вас нет прав для использования этой команды!")
        return
    
    global LOG_CHANNEL_ID
    
    if channel:
        LOG_CHANNEL_ID = channel.id
        await ctx.send(f"✅ Канал для логов установлен: {channel.mention}")
        
        test_embed = discord.Embed(
            title="📋 Система логов активирована",
            description="Все действия модераторов будут логироваться здесь.",
            color=discord.Color.green()
        )
        await channel.send(embed=test_embed)
    else:
        LOG_CHANNEL_ID = None
        await ctx.send("❌ Логи отключены. Укажите канал: !logs #канал")

@bot.event
async def on_command_error(ctx, error):
    """Обработка ошибок команд"""
    if isinstance(error, commands.CheckFailure):
        await ctx.send("❌ У вас нет прав для использования этой команды!")
    else:
        await ctx.send(f"❌ Ошибка: {str(error)}")

# ========== КЛАССЫ ДЛЯ ЗАЯВЛЕНИЙ ==========
class ApplicationModal(Modal):
    """Модальное окно для заполнения заявления"""
    def __init__(self, position: str):
        super().__init__(title=f"Заявление на должность: {position}")
        self.position = position
        
        self.add_item(TextInput(label="Ваше имя", placeholder="Введите ваше имя...", required=True))
        self.add_item(TextInput(label="Ваш возраст", placeholder="Сколько вам лет?", required=True))
        self.add_item(TextInput(label="Как давно играете на сервере", placeholder="Например: 3 месяца", required=True))
        self.add_item(TextInput(label="Причина подачи заявления", placeholder="Почему хотите стать частью команды?", style=discord.TextStyle.paragraph, required=True))
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        # Собираем данные
        name = self.children[0].value
        age = self.children[1].value
        playtime = self.children[2].value
        reason = self.children[3].value
        
        # Отправляем заявку админам
        await send_application_to_admins(interaction, self.position, name, age, playtime, reason)
        
        await interaction.followup.send("✅ Ваше заявление отправлено на рассмотрение!", ephemeral=True)

class ApplicationSelect(Select):
    """Выбор должности для заявления"""
    def __init__(self):
        options = [
            discord.SelectOption(label="📹 Медиа-команда", value="media", description="Создание контента, видео, оформление"),
            discord.SelectOption(label="🛡️ Младший модератор", value="junior_moder", description="Помощь в модерировании чата")
        ]
        super().__init__(placeholder="Выберите должность...", min_values=1, max_values=1, options=options)
    
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ApplicationModal(self.values[0]))

class ApplicationView(View):
    """Панель подачи заявлений"""
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ApplicationSelect())

async def send_application_to_admins(interaction: discord.Interaction, position: str, name: str, age: str, playtime: str, reason: str):
    """Отправка заявки админам в ЛС"""
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
    
    # Отправляем админам
    for role_id in APPLICATION_MANAGER_ROLES:
        role = guild.get_role(role_id)
        if role:
            for member in role.members:
                try:
                    await member.send(embed=embed, view=view)
                except:
                    pass

class ApplicationResponseView(View):
    """Кнопки для ответа на заявку"""
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
        
        return member.guild_permissions.administrator
    
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

# ========== КЛАССЫ ДЛЯ ТИКЕТОВ ==========
class TicketSelect(Select):
    """Выпадающее меню для выбора типа тикета"""
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
    """Панель создания тикетов"""
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketSelect())

class TicketControlView(View):
    """Панель управления тикетом"""
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
    """Создание нового тикета"""
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

# ========== КОМАНДЫ ДЛЯ АДМИНОВ ==========
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

@bot.command()
@commands.has_permissions(administrator=True)
async def add_user(ctx, user: discord.Member):
    """Добавить пользователя в тикет"""
    if ctx.channel.category_id != TICKET_CATEGORY_ID:
        await ctx.send("❌ Команда работает только в каналах тикетов!")
        return
    
    await ctx.channel.set_permissions(user, read_messages=True, send_messages=True)
    await ctx.send(f"✅ {user.mention} добавлен в тикет.")

@bot.command()
@commands.has_permissions(administrator=True)
async def remove_user(ctx, user: discord.Member):
    """Удалить пользователя из тикета"""
    if ctx.channel.category_id != TICKET_CATEGORY_ID:
        await ctx.send("❌ Команда работает только в каналах тикетов!")
        return
    
    await ctx.channel.set_permissions(user, overwrite=None)
    await ctx.send(f"✅ {user.mention} удален из тикета.")

@bot.command()
@commands.has_permissions(administrator=True)
async def rename_ticket(ctx, *, new_name: str):
    """Переименовать тикет"""
    if ctx.channel.category_id != TICKET_CATEGORY_ID:
        await ctx.send("❌ Команда работает только в каналах тикетов!")
        return
    
    await ctx.channel.edit(name=new_name)
    await ctx.send(f"✅ Канал переименован в: {new_name}")

@bot.event
async def on_ready():
    print(f"✅ Бот {bot.user} запущен!")
    print(f"📁 Категория тикетов ID: {TICKET_CATEGORY_ID}")
    print(f"📢 Канал наказаний ID: {PUNISHMENT_CHANNEL_ID}")
    print(f"👥 MOD ролей: {len(MOD_ROLES)}")
    
    bot.add_view(TicketPanelView())
    bot.add_view(ApplicationView())
    
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
